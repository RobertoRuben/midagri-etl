"""Carga de precios de un mercado: portal SISAP → validación → (kg en Ciudades) → `BM_MarketPrice`
(y `BM_CatalogPrice` si es 15011501)."""

import asyncio
import logging
from datetime import UTC, date, datetime

import polars as pl
from asyncer import asyncify

from app.modules.common.db.decorator.transactional import transactional
from app.modules.midagri.model.mssql import Market
from app.modules.midagri.model.pg.enums import LoadStatus
from app.modules.midagri.model.sisap import MarketRef, SisapSource
from app.modules.midagri.repository.interface.catalog_repository import CatalogRepository
from app.modules.midagri.repository.interface.crop_repository import CropRepository
from app.modules.midagri.repository.interface.price_repository import REPORT_MARKET_CODE, PriceRepository, UpsertResult
from app.modules.midagri.repository.interface.sisap_repository import SisapRepository
from app.modules.midagri.repository.interface.ubigeo_repository import UbigeoRepository
from app.modules.midagri.service.impl.gap_service_impl import fetch_error_warning
from app.modules.midagri.service.interface.ingestion_service import IngestionService, MarketIngestion
from app.modules.midagri.utils.gap_classifier import attach_last_prices, priced_varieties, relevant_genres
from app.modules.midagri.utils.price_pipeline import to_kg, to_upsert_rows, validate_prices
from app.modules.midagri.utils.trace import format_trace

logger = logging.getLogger(__name__)


class IngestionServiceImpl(IngestionService):
    """Una transacción de SQL Server por mercado (`@transactional` sobre la sesión del repositorio de precios).

    Los repositorios de SQL Server comparten la misma sesión. El portal se consulta fuera de la transacción:
    solo el upsert la abre.
    """

    __session_attr__ = "price_repository.session"

    def __init__(
        self,
        sisap_repository: SisapRepository,
        crop_repository: CropRepository,
        catalog_repository: CatalogRepository,
        ubigeo_repository: UbigeoRepository,
        price_repository: PriceRepository,
    ) -> None:
        self.sisap_repository = sisap_repository
        self.crop_repository = crop_repository
        self.catalog_repository = catalog_repository
        self.ubigeo_repository = ubigeo_repository
        self.price_repository = price_repository

    async def ingest_market(
        self, market: Market, date_from: date, date_to: date, *, dry_run: bool = False
    ) -> MarketIngestion:
        source: SisapSource = "CIUDADES" if market.source == "CIUDADES" else "MAYORISTA"
        ref = MarketRef(source, market.code, market.name)
        outcome = MarketIngestion(market=ref, date_from=date_from, date_to=date_to, started_at=datetime.now(UTC))
        try:
            await self._ingest(market.id, ref, outcome, dry_run=dry_run)
        except Exception as error:  # un mercado caído no bloquea a los demás
            logger.exception("Ingesta de %s falló", ref.label)
            outcome.status = LoadStatus.FAILED
            outcome.error = f"{type(error).__name__}: {error}"
            outcome.traceback = format_trace()
        outcome.finished_at = datetime.now(UTC)
        return outcome

    async def _ingest(self, market_id: int, ref: MarketRef, outcome: MarketIngestion, *, dry_run: bool) -> None:
        crops = await self.crop_repository.frame_all()
        inactive = set(crops.filter(~pl.col("active"))["code"].to_list())
        genres = relevant_genres(await self.sisap_repository.list_genres(ref.source, ref.code), inactive)
        variety_lists = await asyncio.gather(
            *(self.sisap_repository.list_varieties(ref.source, genre.code) for genre in genres)
        )
        varieties = [variety for batch in variety_lists for variety in batch]
        if not varieties:
            outcome.status = LoadStatus.SKIPPED
            outcome.error = "El portal no publicó géneros agrícolas para este mercado."
            return

        result = await self.sisap_repository.fetch_prices(
            ref.source, ref.code, varieties, outcome.date_from, outcome.date_to
        )
        outcome.fetched = result.rows.height
        outcome.fetch_errors = [fetch_error_warning(ref, error) for error in result.errors]
        outcome.priced = priced_varieties(result.rows, varieties, {g.code: g.name for g in genres}, ref.label)

        named = result.rows.filter(pl.col("variety_code").is_not_null())
        valid, invalid = await asyncify(validate_prices)(named)
        rejected = [invalid]
        if ref.source == "CIUDADES":
            valid, not_convertible = await asyncify(to_kg)(valid)
            rejected.append(not_convertible)
        outcome.priced = await asyncify(attach_last_prices)(outcome.priced, valid)  # precio en S/ por kg

        catalog_ids = await self.catalog_repository.map_active_by_code(valid["variety_code"].unique().to_list())
        region_lookup = await self.ubigeo_repository.region_lookup()
        upsert = await asyncify(to_upsert_rows)(
            valid, market_id=market_id, catalog_ids=catalog_ids, region_lookup=region_lookup
        )
        rejected.append(upsert.rejected)
        outcome.rejected = pl.concat(rejected)
        outcome.matched = upsert.rows.height
        outcome.unmatched = upsert.unmatched + (result.rows.height - named.height)
        outcome.unmatched_codes = upsert.unmatched_codes

        if not dry_run:
            saved, report = await self._save(upsert.rows, to_report=ref.code == REPORT_MARKET_CODE)
            outcome.inserted, outcome.updated, outcome.unchanged = saved.inserted, saved.updated, saved.unchanged
            if report is not None:
                outcome.report_inserted, outcome.report_updated = report.inserted, report.updated
        outcome.status = LoadStatus.PARTIAL if result.errors else LoadStatus.OK
        logger.info(
            "Ingesta %s: %s descargadas, %s cargadas (%s nuevas, %s actualizadas), %s sin catálogo, %s rechazadas",
            ref.label,
            outcome.fetched,
            outcome.matched,
            outcome.inserted,
            outcome.updated,
            outcome.unmatched,
            outcome.rejected.height,
        )

    @transactional
    async def _save(self, rows: pl.DataFrame, *, to_report: bool) -> tuple[UpsertResult, UpsertResult | None]:
        """Guarda en `BM_MarketPrice` y, si es el mercado del reporte, también en `BM_CatalogPrice` (misma transacción)."""
        saved = await self.price_repository.upsert(rows)
        report = await self.price_repository.upsert_report(rows) if to_report else None
        return saved, report
