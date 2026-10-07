"""Reporte de faltantes: portal SISAP (HTTP) + multi gestión y catálogo (SQL Server). Solo lee."""

import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime

import polars as pl
from asyncer import asyncify

from app.modules.midagri.dto.response.gap_report_response import GapItemResponse, GapReportResponse
from app.modules.midagri.model.sisap import FetchError, MarketRef, SisapVariety
from app.modules.midagri.repository.interface.catalog_repository import CatalogRepository
from app.modules.midagri.repository.interface.crop_repository import CropRepository
from app.modules.midagri.repository.interface.sisap_repository import SisapRepository
from app.modules.midagri.service.interface.gap_service import GapService
from app.modules.midagri.utils.gap_classifier import (
    PRICED_SCHEMA,
    attach_last_prices,
    classify_gaps,
    priced_varieties,
    relevant_genres,
)
from app.modules.midagri.utils.price_pipeline import to_kg, validate_prices

logger = logging.getLogger(__name__)


class GapServiceImpl(GapService):
    """Faltantes ESC1/ESC2 bajo cultivos activos (D6), familias agrícolas 01–09 (D5)."""

    def __init__(
        self,
        sisap_repository: SisapRepository,
        crop_repository: CropRepository,
        catalog_repository: CatalogRepository,
    ) -> None:
        self.sisap_repository = sisap_repository
        self.crop_repository = crop_repository
        self.catalog_repository = catalog_repository

    async def build_report(self, markets: Sequence[MarketRef], date_from: date, date_to: date) -> GapReportResponse:
        _validate(markets, date_from, date_to)
        crops = await self.crop_repository.frame_all()
        inactive_crops = set(crops.filter(~pl.col("active"))["code"].to_list())
        warnings: list[str] = []
        priced_frames: list[pl.DataFrame] = []
        for market in markets:
            try:
                priced, market_warnings = await self._priced_in_market(market, inactive_crops, date_from, date_to)
            except Exception as error:  # el portal cayó para este mercado: el reporte sigue con los demás
                logger.warning("Faltantes: no se pudo consultar %s: %s", market.label, error)
                warnings.append(f"{market.label}: no se pudo consultar el portal ({type(error).__name__}: {error})")
                continue
            priced_frames.append(priced)
            warnings.extend(market_warnings)
        return await self._report(markets, date_from, date_to, priced_frames, warnings, crops)

    async def build_report_from_priced(
        self,
        markets: Sequence[MarketRef],
        date_from: date,
        date_to: date,
        priced: Sequence[pl.DataFrame],
        warnings: Sequence[str] = (),
    ) -> GapReportResponse:
        _validate(markets, date_from, date_to)
        return await self._report(markets, date_from, date_to, priced, list(warnings), None)

    async def _report(
        self,
        markets: Sequence[MarketRef],
        date_from: date,
        date_to: date,
        priced_frames: Sequence[pl.DataFrame],
        warnings: list[str],
        crops: pl.DataFrame | None,
    ) -> GapReportResponse:
        crops = crops if crops is not None else await self.crop_repository.frame_all()
        priced_all = pl.concat(priced_frames) if priced_frames else pl.DataFrame(schema=PRICED_SCHEMA)
        codes = priced_all["variety_code"].unique().to_list()
        existing = {catalog.code for catalog in await self.catalog_repository.find_by_codes(codes) if catalog.code}
        gaps = await asyncify(classify_gaps)(priced_all, crops, existing)
        items = [GapItemResponse.model_validate(row) for row in gaps.to_dicts()]
        return GapReportResponse(
            generated_at=datetime.now(UTC),
            date_from=date_from,
            date_to=date_to,
            markets=[market.label for market in markets],
            items=items,
            total_esc1=sum(item.status == "ESC1" for item in items),
            total_esc2=sum(item.status == "ESC2" for item in items),
            warnings=warnings,
        )

    async def _priced_in_market(
        self, market: MarketRef, inactive_crops: set[str], date_from: date, date_to: date
    ) -> tuple[pl.DataFrame, list[str]]:
        """Variedades con precio en el periodo en un mercado (consulta el portal)."""
        genres = relevant_genres(await self.sisap_repository.list_genres(market.source, market.code), inactive_crops)
        variety_lists = await asyncio.gather(
            *(self.sisap_repository.list_varieties(market.source, genre.code) for genre in genres)
        )
        varieties: list[SisapVariety] = [variety for batch in variety_lists for variety in batch]
        if not varieties:
            return pl.DataFrame(schema=PRICED_SCHEMA), []
        result = await self.sisap_repository.fetch_prices(market.source, market.code, varieties, date_from, date_to)
        priced = priced_varieties(result.rows, varieties, {g.code: g.name for g in genres}, market.label)
        priced = await asyncify(_with_prices)(priced, result.rows, market)
        logger.info("Faltantes: %s con %s variedades con precio", market.label, priced.height)
        return priced, [fetch_error_warning(market, error) for error in result.errors]


def _with_prices(priced: pl.DataFrame, rows: pl.DataFrame, market: MarketRef) -> pl.DataFrame:
    """Precio del último día en S/ por kg, con las mismas reglas de calidad y conversión que la ingesta."""
    valid, _ = validate_prices(rows.filter(pl.col("variety_code").is_not_null()))
    if market.source == "CIUDADES":
        valid, _ = to_kg(valid)
    return attach_last_prices(priced, valid)


def fetch_error_warning(market: MarketRef, error: FetchError) -> str:
    """Texto de advertencia de un lote que no se pudo descargar."""
    return (
        f"{market.label}: {len(error.variety_codes)} variedades sin consultar "
        f"({error.date_from:%d/%m/%Y}–{error.date_to:%d/%m/%Y}): {error.message}"
    )


def _validate(markets: Sequence[MarketRef], date_from: date, date_to: date) -> None:
    if not markets:
        raise ValueError("Se necesita al menos un mercado para calcular los faltantes.")
    if date_from > date_to:
        raise ValueError(f"'date_from' ({date_from}) no puede ser posterior a 'date_to' ({date_to})")
