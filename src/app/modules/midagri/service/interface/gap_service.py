"""Contrato del reporte de faltantes del catálogo."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date

import polars as pl

from app.modules.midagri.dto.response.gap_report_response import GapReportResponse
from app.modules.midagri.model.sisap import MarketRef


class GapService(ABC):
    """Cruza lo que SISAP publica con precio contra el catálogo y la multi gestión. Solo lee."""

    @abstractmethod
    async def build_report(self, markets: Sequence[MarketRef], date_from: date, date_to: date) -> GapReportResponse:
        """Faltantes ESC1/ESC2 de los mercados en el periodo.

        Un mercado o un lote que falla en el portal no aborta el reporte: queda en `warnings`.

        Raises:
            ValueError: Si `date_from` es posterior a `date_to` o no hay mercados.
        """

    @abstractmethod
    async def build_report_from_priced(
        self,
        markets: Sequence[MarketRef],
        date_from: date,
        date_to: date,
        priced: Sequence[pl.DataFrame],
        warnings: Sequence[str] = (),
    ) -> GapReportResponse:
        """Faltantes a partir de variedades con precio ya descargadas (la ingesta del ETL): sin consultar el portal.

        Args:
            priced: Un DataFrame por mercado con `PRICED_SCHEMA` (`utils/gap_classifier.py`).
            warnings: Advertencias de la descarga (lotes fallidos), que pasan al reporte.
        """
