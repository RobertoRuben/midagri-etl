"""Contrato de la carga de precios de un mercado."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime

import polars as pl

from app.modules.midagri.model.mssql import Market
from app.modules.midagri.model.pg.enums import LoadStatus
from app.modules.midagri.model.sisap import MarketRef
from app.modules.midagri.utils.gap_classifier import PRICED_SCHEMA
from app.modules.midagri.utils.price_pipeline import empty_rejected


@dataclass(slots=True)
class MarketIngestion:
    """Resultado de cargar un mercado. Lo usa el ETL para `price_load`, el log, el correo y los faltantes.

    Attributes:
        fetched: Filas descargadas del portal.
        matched: Filas listas para `BM_MarketPrice` (con `idCatalog` e `idUbigeo`), tras consolidar.
        inserted / updated / unchanged: Resultado del upsert en `BM_MarketPrice` (0 en un `dry_run`).
        report_inserted / report_updated: Resultado en `BM_CatalogPrice`; solo el mercado 15011501 (D15').
        unmatched: Filas sin producto activo en el catálogo (sus códigos en `unmatched_codes`).
        rejected: Filas descartadas por calidad, con su motivo (`REJECTED_SCHEMA`).
        fetch_errors: Lotes que no se pudieron descargar (hacen la carga `partial`).
        priced: Variedades con precio (`PRICED_SCHEMA`), para el reporte de faltantes sin volver al portal.
    """

    market: MarketRef
    date_from: date
    date_to: date
    started_at: datetime
    status: LoadStatus = LoadStatus.OK
    finished_at: datetime | None = None
    fetched: int = 0
    matched: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    report_inserted: int = 0
    report_updated: int = 0
    unmatched: int = 0
    unmatched_codes: list[str] = field(default_factory=list)
    rejected: pl.DataFrame = field(default_factory=empty_rejected)
    fetch_errors: list[str] = field(default_factory=list)
    priced: pl.DataFrame = field(default_factory=lambda: pl.DataFrame(schema=PRICED_SCHEMA))
    error: str | None = None
    traceback: str | None = None
    """Traza de la excepción si el mercado falló (va al log y al correo de incidencias, D37)."""


class IngestionService(ABC):
    """Descarga los precios de un mercado del portal y los carga en `BM_MarketPrice` (y 15011501 en `BM_CatalogPrice`)."""

    @abstractmethod
    async def ingest_market(
        self, market: Market, date_from: date, date_to: date, *, dry_run: bool = False
    ) -> MarketIngestion:
        """Carga un mercado en **una** transacción. Nunca lanza: un fallo queda en el resultado (`failed`).

        Args:
            market: Mercado de `BM_Market` (activo).
            date_from: Primer día de la ventana.
            date_to: Último día de la ventana.
            dry_run: Si es True, descarga, valida y cuenta, pero no escribe en SQL Server.
        """
