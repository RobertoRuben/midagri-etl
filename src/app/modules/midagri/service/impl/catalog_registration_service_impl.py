"""Registro de faltantes con los SP del app: cultivos (`Cultivos`, D34) y productos (`Registro`, D33).

Entradas: la subida del Excel o, al final de cada ejecución, los faltantes del reporte (alta automática, D36).

Primero los cultivos (`uspIT_GuardarActualizarMultivalores`), después los productos (`uspBM_SaveUpdateCatalogo`).
Dos bases, sin transacción entre ellas: cada alta se confirma en SQL Server y **después** se registra su resultado
en PostgreSQL (`catalog_load_item`).
"""

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl
from asyncer import asyncify
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.exception import ConflictException, NotFoundException, UnprocessableEntityException
from app.modules.common.pagination.paginated import Paginated
from app.modules.common.pagination.pagination_meta import PaginationMeta
from app.modules.midagri.dto.response.catalog_registration_response import (
    CatalogRegistrationItemResponse,
    CatalogRegistrationResponse,
    CatalogRegistrationSummaryResponse,
)
from app.modules.midagri.dto.response.gap_report_response import GapItemResponse
from app.modules.midagri.model.pg import CatalogLoad, CatalogLoadItem
from app.modules.midagri.model.pg.enums import CatalogLoadStatus, RegistrationOutcome
from app.modules.midagri.repository.interface.catalog_load_repository import CatalogLoadRepository
from app.modules.midagri.repository.interface.catalog_repository import CatalogRepository, SpResult
from app.modules.midagri.repository.interface.crop_repository import CropRepository
from app.modules.midagri.service.interface.catalog_registration_service import CatalogRegistrationService
from app.modules.midagri.utils.registration_sheet import (
    CROP_HEADERS,
    CROP_SHEET,
    REGISTRATION_HEADERS,
    REGISTRATION_SHEET,
    RegistrationRow,
    crop_rows,
    normalize_code,
    read_crop_sheet,
    read_registration_sheet,
    registration_rows,
    sheet_frame,
    validate_crops,
    validate_registration,
)

logger = logging.getLogger(__name__)

REGISTERED_BY = "etl-sisap"
"""`registeredBy` / `UsuarioCreacion` (varchar 20). Quién subió el archivo queda en `catalog_load.requested_by`."""
NOT_APPLIED = "No se registró: hay filas inválidas en el archivo"
CROP, PRODUCT = "crop", "product"

Outcome = tuple[RegistrationOutcome, str | None]


@dataclass(frozen=True, slots=True)
class _Sheets:
    """Las dos hojas ya validadas y lo que ya existe en la base."""

    crops: list[RegistrationRow]
    products: list[RegistrationRow]
    existing_crops: set[str]
    """Cultivos de la hoja que ya existen activos (se omiten)."""
    existing_products: set[str]

    @property
    def has_invalid(self) -> bool:
        return any(not row.valid for row in (*self.crops, *self.products))


class CatalogRegistrationServiceImpl(CatalogRegistrationService):
    """`catalog_repository` y `crop_repository` usan `mssql`; `load_repository` usa `pg` (las mismas sesiones).

    Las confirmaciones son explícitas: una por alta en SQL Server y una por fila registrada en PostgreSQL.
    """

    def __init__(
        self,
        catalog_repository: CatalogRepository,
        crop_repository: CropRepository,
        load_repository: CatalogLoadRepository,
        *,
        mssql: AsyncSession,
        pg: AsyncSession,
    ) -> None:
        self.catalog_repository = catalog_repository
        self.crop_repository = crop_repository
        self.load_repository = load_repository
        self.mssql = mssql
        self.pg = pg

    async def register(
        self, file_name: str, content: bytes, *, dry_run: bool, requested_by: str | None
    ) -> CatalogRegistrationResponse:
        sheets = await self._validate(content)
        load = CatalogLoad(
            file_name=file_name[:200],
            file_sha256=hashlib.sha256(content).hexdigest(),
            requested_by=requested_by,
            dry_run=dry_run,
        )
        return await self._run(load, sheets, dry_run=dry_run)

    async def register_gaps(
        self, items: Sequence[GapItemResponse], *, etl_run_id: int, dry_run: bool
    ) -> CatalogRegistrationResponse:
        crop_sheet = sheet_frame(crop_rows(items), CROP_HEADERS)
        product_sheet = sheet_frame(registration_rows(items), REGISTRATION_HEADERS)
        sheets = await self._check(crop_sheet, product_sheet)
        codes = ",".join(sorted(item.variety_code for item in items))
        load = CatalogLoad(
            file_name=f"etl-run-{etl_run_id}",
            file_sha256=hashlib.sha256(codes.encode()).hexdigest(),
            requested_by=REGISTERED_BY,
            dry_run=dry_run,
            etl_run_id=etl_run_id,
        )
        return await self._run(load, sheets, dry_run=dry_run)

    async def list_loads(self, page: int, size: int) -> Paginated[CatalogRegistrationSummaryResponse]:
        loads, total = await self.load_repository.list_recent(page, size)
        return Paginated[CatalogRegistrationSummaryResponse](
            data=[CatalogRegistrationSummaryResponse.model_validate(load) for load in loads],
            pagination=PaginationMeta.build(page=page, page_size=size, total_items=total),
        )

    async def get_load(self, catalog_load_id: int) -> CatalogRegistrationResponse:
        load = await self.load_repository.get_by_id(catalog_load_id)
        if load is None:
            raise NotFoundException(f"No existe la subida {catalog_load_id}.")
        return _response(load, await self.load_repository.list_items(catalog_load_id))

    # --- Pasos ---------------------------------------------------------------------------------

    async def _run(self, load: CatalogLoad, sheets: _Sheets, *, dry_run: bool) -> CatalogRegistrationResponse:
        """Guarda el plan (con `dry_run` o filas inválidas) o registra: cultivos primero, después productos."""
        load.status = CatalogLoadStatus.INVALID if sheets.has_invalid else CatalogLoadStatus.VALIDATED
        load.total_rows = len(sheets.crops) + len(sheets.products)
        if dry_run or sheets.has_invalid:
            return await self._save_plan(load, sheets)

        if await self.catalog_repository.sp_uses_correlative():
            raise ConflictException(
                "uspBM_SaveUpdateCatalogo reemplaza el código por un correlativo en esta base: no se registra nada "
                "(el código SISAP se perdería)."
            )
        load.status = CatalogLoadStatus.FAILED  # hasta terminar; si el proceso se corta, queda así
        load = await self.load_repository.save(load)
        await self.pg.commit()

        items: list[CatalogLoadItem] = []
        failed_crops: set[str] = set()
        for row in sheets.crops:
            outcome = await self._create_crop(row, sheets.existing_crops)
            if outcome[0] is RegistrationOutcome.ERROR:
                failed_crops.add(row.code)
            items.append(await self._record(load.id, CROP, row, outcome))
        for row in sheets.products:
            if row.crop_code in failed_crops:
                outcome = (RegistrationOutcome.ERROR, f"No se creó su cultivo {row.crop_code}")
            else:
                outcome = await self._create_product(row, sheets.existing_products)
            items.append(await self._record(load.id, PRODUCT, row, outcome))

        _count(load, items)
        if load.errors == 0:
            load.status = CatalogLoadStatus.APPLIED
        else:
            load.status = CatalogLoadStatus.PARTIAL if load.created else CatalogLoadStatus.FAILED
        await self.pg.commit()
        logger.info(
            "Registro %s (%s): %s creados, %s ya existían, %s errores",
            load.id,
            load.file_name,
            load.created,
            load.skipped,
            load.errors,
        )
        return _response(load, items)

    async def _validate(self, content: bytes) -> _Sheets:
        try:
            product_sheet = await asyncify(read_registration_sheet)(content)
            crop_sheet = await asyncify(read_crop_sheet)(content)
        except ValueError as error:
            raise UnprocessableEntityException(str(error)) from error
        if product_sheet.is_empty() and crop_sheet.is_empty():
            raise UnprocessableEntityException(f"Las hojas '{CROP_SHEET}' y '{REGISTRATION_SHEET}' no tienen filas.")
        return await self._check(crop_sheet, product_sheet)

    async def _check(self, crop_sheet: pl.DataFrame, product_sheet: pl.DataFrame) -> _Sheets:
        """Valida las dos hojas contra la multi gestión y el catálogo (mismas reglas para el Excel y el ETL)."""
        frame = await self.crop_repository.frame_all()
        crop_status = {
            code: (name, active) for code, name, active in frame.select("code", "name", "active").iter_rows()
        }
        crops = validate_crops(crop_sheet, crop_status)
        # Los productos pueden colgar de un cultivo que se crea en esta misma subida.
        known = dict(crop_status)
        known.update({row.code: (row.name, True) for row in crops if row.valid and row.code not in crop_status})

        codes = [normalize_code(raw) for raw in product_sheet["Código"].to_list()]
        existing = {catalog.code for catalog in await self.catalog_repository.find_by_codes(codes) if catalog.code}
        return _Sheets(
            crops=crops,
            products=validate_registration(product_sheet, known, existing),
            existing_crops={row.code for row in crops if row.valid and row.code in crop_status},
            existing_products=existing,
        )

    async def _save_plan(self, load: CatalogLoad, sheets: _Sheets) -> CatalogRegistrationResponse:
        load = await self.load_repository.save(load)
        plan = [
            (CROP, row, _planned(row, sheets.existing_crops, has_invalid=sheets.has_invalid)) for row in sheets.crops
        ] + [
            (PRODUCT, row, _planned(row, sheets.existing_products, has_invalid=sheets.has_invalid))
            for row in sheets.products
        ]
        items = [_item(load.id, kind, row, outcome) for kind, row, outcome in plan]
        for item in items:
            await self.load_repository.add_item(item)
        _count(load, items)
        await self.pg.commit()
        return _response(load, items)

    async def _record(self, load_id: int, kind: str, row: RegistrationRow, outcome: Outcome) -> CatalogLoadItem:
        item = _item(load_id, kind, row, outcome)
        await self.load_repository.add_item(item)
        await self.pg.commit()
        return item

    async def _create_crop(self, row: RegistrationRow, existing: set[str]) -> Outcome:
        """Alta de un cultivo en su propia transacción. Nunca lanza: un fallo queda como `error`."""
        if row.code in existing:
            return RegistrationOutcome.SKIPPED_EXISTS, _detail(row.warnings)
        try:
            if await self.crop_repository.exists_any(row.code):  # el SP solo valida contra los activos
                return RegistrationOutcome.ERROR, f"Ya hay una fila de BM_TCATCAT con el código {row.code}"
            result = await self.crop_repository.create_via_sp(code=row.code, name=row.name, user=REGISTERED_BY)
            failure = await self._sp_failure(result)
            if failure:
                return RegistrationOutcome.ERROR, failure
            crop = await self.crop_repository.find_by_code(row.code)
            if crop is None or not crop.activo:
                await self.mssql.rollback()
                return RegistrationOutcome.ERROR, "El SP no dejó el cultivo activo con ese código; no se registró"
            await self.mssql.commit()
        except Exception as error:  # una fila caída no detiene las demás
            logger.exception("Alta del cultivo %s falló", row.code)
            await self.mssql.rollback()
            return RegistrationOutcome.ERROR, f"{type(error).__name__}: {error}"
        return RegistrationOutcome.CREATED, _detail(row.warnings)

    async def _create_product(self, row: RegistrationRow, existing: set[str]) -> Outcome:
        """Alta de un producto en su propia transacción. Nunca lanza: un fallo queda como `error`."""
        if row.code in existing or await self.catalog_repository.exists_code(row.code):
            return RegistrationOutcome.SKIPPED_EXISTS, _detail(row.warnings)
        try:
            crop = await self.crop_repository.find_by_code(row.crop_code)
            if crop is None or not crop.activo:
                return RegistrationOutcome.ERROR, f"El cultivo {row.crop_code} ya no está activo"
            result = await self.catalog_repository.create_via_sp(
                code=row.code, name=row.name, crop_code=row.crop_code, user=REGISTERED_BY
            )
            failure = await self._sp_failure(result)
            if failure:
                return RegistrationOutcome.ERROR, failure
            if not await self.catalog_repository.exists_code(row.code):
                await self.mssql.rollback()
                return RegistrationOutcome.ERROR, "El SP no guardó el código SISAP; no se registró"
            await self.mssql.commit()
        except Exception as error:  # una fila caída no detiene las demás
            logger.exception("Alta de %s falló", row.code)
            await self.mssql.rollback()
            return RegistrationOutcome.ERROR, f"{type(error).__name__}: {error}"
        return RegistrationOutcome.CREATED, _detail(row.warnings)

    async def _sp_failure(self, result: SpResult) -> str | None:
        """Motivo del fallo del SP (y deshace la transacción), o `None` si salió bien."""
        if not result.transaction_open:
            await self.mssql.rollback()
            return f"El SP revirtió la transacción: {result.message}"
        if not result.ok:
            await self.mssql.rollback()
            return f"El SP rechazó el alta: {result.message}"
        return None


def _planned(row: RegistrationRow, existing: set[str], *, has_invalid: bool) -> Outcome:
    if not row.valid:
        return RegistrationOutcome.INVALID, _detail(row.errors + row.warnings)
    if row.code in existing:
        return RegistrationOutcome.SKIPPED_EXISTS, _detail(row.warnings)
    warnings = [NOT_APPLIED, *row.warnings] if has_invalid else row.warnings
    return RegistrationOutcome.PLANNED, _detail(warnings)


def _detail(messages: list[str]) -> str | None:
    return "; ".join(messages) or None


def _item(load_id: int, kind: str, row: RegistrationRow, outcome: Outcome) -> CatalogLoadItem:
    return CatalogLoadItem(
        catalog_load_id=load_id,
        kind=kind,
        row_number=row.row_number,
        code=row.code[:20],
        name=row.name[:200],
        crop_code=row.crop_code[:10],
        outcome=outcome[0],
        detail=outcome[1],
    )


def _count(load: CatalogLoad, items: list[CatalogLoadItem]) -> None:
    outcomes = [item.outcome for item in items]
    load.planned = outcomes.count(RegistrationOutcome.PLANNED)
    load.created = outcomes.count(RegistrationOutcome.CREATED)
    load.skipped = outcomes.count(RegistrationOutcome.SKIPPED_EXISTS)
    load.invalid = outcomes.count(RegistrationOutcome.INVALID)
    load.errors = outcomes.count(RegistrationOutcome.ERROR)


def _response(load: CatalogLoad, items: list[CatalogLoadItem]) -> CatalogRegistrationResponse:
    summary = CatalogRegistrationSummaryResponse.model_validate(load)
    return CatalogRegistrationResponse(
        **summary.model_dump(),
        items=[CatalogRegistrationItemResponse.model_validate(item) for item in items],
    )
