"""Catálogo de productos de mercado (`BM_Catalog`) en SQL Server: lecturas y alta con el SP del app."""

import logging
from collections.abc import Sequence
from itertools import batched

import polars as pl
from sqlalchemy import ColumnElement, and_, false, select, text, true
from sqlalchemy.exc import ResourceClosedError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.repository.impl.generic_repository_impl import GenericRepositoryImpl
from app.modules.midagri.model.mssql import Catalog
from app.modules.midagri.repository.interface.catalog_repository import CatalogRepository, SpResult
from app.modules.midagri.utils.catalog_constants import CATALOG_TYPE_MARKET, ORGANIZATION_ID
from app.modules.midagri.utils.catalog_lookup import first_id_by_code

logger = logging.getLogger(__name__)

IN_CLAUSE_BATCH = 1000
"""Tamaño de cada lote de un `IN (...)`: SQL Server acepta hasta 2100 parámetros por consulta."""

CATALOG_FRAME_SCHEMA: dict[str, type[pl.DataType]] = {
    "id": pl.Int64,
    "code": pl.String,
    "name": pl.String,
    "category": pl.String,
}


_CREATE = text(
    "SET NOCOUNT ON; "
    "EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type=:type, @category=:category, @subCategory=NULL, "
    "@code=:code, @name=:name, @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, "
    "@maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, "
    "@grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=:organization, @active=1, "
    "@User=:user, @imagenUrl=NULL;"
)
"""Mismos parámetros que el alta validada en QAS (`sql/verificacion_carga_catalogo_qas.sql`), con valores enlazados."""


def _is_market_product() -> ColumnElement[bool]:
    return Catalog.type == CATALOG_TYPE_MARKET


def _is_active() -> ColumnElement[bool]:
    # `IS 1` no es válido en SQL Server para `bit`: se compara con `true()`/`false()` (`= 1`, `= 0`).
    return and_(Catalog.active == true(), Catalog.deleted == false())


class CatalogRepositoryImpl(GenericRepositoryImpl[Catalog], CatalogRepository):
    """Productos de mercado (`type='0001'`). Solo inserta con el SP del app (D33); nunca actualiza ni borra."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Catalog, session)

    async def map_active_by_code(self, codes: Sequence[str]) -> dict[str, int]:
        unique_codes = sorted(set(codes))
        rows: list[dict[str, object]] = []
        for batch in batched(unique_codes, IN_CLAUSE_BATCH, strict=False):
            stmt = select(Catalog.code, Catalog.id).where(_is_market_product(), _is_active(), Catalog.code.in_(batch))
            rows.extend(dict(row) for row in (await self.session.execute(stmt)).mappings())
        mapping, duplicates = first_id_by_code(pl.DataFrame(rows, schema={"code": pl.String, "id": pl.Int64}))
        for code, ids in duplicates.iter_rows():
            logger.warning("Código %s repetido en BM_Catalog (ids %s); se usa el id %s", code, ids, min(ids))
        return dict(mapping.iter_rows())

    async def exists_code(self, code: str) -> bool:
        stmt = select(Catalog.id).where(_is_market_product(), Catalog.code == code).limit(1)
        return await self.session.scalar(stmt) is not None

    async def find_by_codes(self, codes: Sequence[str]) -> list[Catalog]:
        found: list[Catalog] = []
        for batch in batched(sorted(set(codes)), IN_CLAUSE_BATCH, strict=False):
            stmt = select(Catalog).where(_is_market_product(), Catalog.code.in_(batch))
            found.extend(await self.session.scalars(stmt))
        return sorted(found, key=lambda catalog: (catalog.code or "", catalog.id))

    async def create_via_sp(self, *, code: str, name: str, crop_code: str, user: str) -> SpResult:
        params = {
            "type": CATALOG_TYPE_MARKET,
            "category": crop_code,
            "code": code,
            "name": name,
            "organization": ORGANIZATION_ID,
            "user": user,
        }
        result = await self.session.execute(_CREATE, params)
        try:
            row = result.mappings().first()
        except ResourceClosedError:  # el SP no devolvió filas
            row = None
        values = {key.lower(): value for key, value in (row or {}).items()}
        # El SP hace ROLLBACK interno si falla: con @@TRANCOUNT = 0 la transacción de la sesión ya no existe.
        open_transactions = await self.session.scalar(text("SELECT @@TRANCOUNT"))
        return SpResult(
            ok=str(values.get("status", "")).strip() in {"1", "True"},
            message=str(values.get("msg") or values.get("message") or ""),
            transaction_open=bool(open_transactions),
        )

    async def sp_uses_correlative(self) -> bool:
        definition = await self.session.scalar(
            text("SELECT OBJECT_DEFINITION(OBJECT_ID(N'dbo.uspBM_SaveUpdateCatalogo'))")
        )
        return "BM_TCATTY" in (definition or "").upper()

    async def frame_active(self) -> pl.DataFrame:
        stmt = (
            select(Catalog.id, Catalog.code, Catalog.name, Catalog.category)
            .where(_is_market_product(), _is_active())
            .order_by(Catalog.code, Catalog.id)
        )
        rows = (await self.session.execute(stmt)).mappings().all()
        return pl.DataFrame([dict(row) for row in rows], schema=CATALOG_FRAME_SCHEMA)
