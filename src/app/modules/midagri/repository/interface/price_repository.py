"""Contratos de mercados (`BM_Market`) y precios (`BM_MarketPrice` y `BM_CatalogPrice`) en SQL Server."""

from dataclasses import dataclass
from typing import Final, Protocol

import polars as pl

from app.modules.common.repository.interface.generic_repository import GenericRepository
from app.modules.midagri.model.mssql import Market, MarketPrice

REPORT_MARKET_CODE: Final[str] = "15011501"
"""Único mercado que también va a `BM_CatalogPrice`: el SP de reportes del app lee esa tabla sin distinguir
mercado, y el legado solo cargaba este (D15')."""

UPSERT_SCHEMA: dict[str, pl.DataType] = {
    "id_catalog": pl.Int64(),
    "id_market": pl.Int64(),
    "id_ubigeo": pl.Int64(),
    "date": pl.Date(),
    "unit_of_measure": pl.String(),
    "type": pl.String(),
    "equivalence": pl.String(),
    "min": pl.Decimal(18, 4),
    "mean": pl.Decimal(18, 4),
    "max": pl.Decimal(18, 4),
    "registered_by": pl.String(),
}
"""Filas listas para cargar. La llave de `BM_MarketPrice` (`UQ_BM_MarketPrice_Key`) son las 6 primeras columnas."""

UPSERT_KEY: tuple[str, ...] = ("id_catalog", "id_market", "id_ubigeo", "date", "unit_of_measure", "type")
REPORT_KEY: tuple[str, ...] = ("id_catalog", "id_ubigeo", "date", "unit_of_measure", "type")
"""Llave lógica de `BM_CatalogPrice` (la del legado, sin mercado)."""


@dataclass(frozen=True, slots=True)
class UpsertResult:
    """Resultado de un upsert: filas nuevas, filas cuyo precio cambió y filas que ya estaban iguales."""

    inserted: int
    updated: int
    unchanged: int


class MarketRepository(GenericRepository[Market], Protocol):
    """Mercados SISAP. Solo lectura desde la API (se activan con un `UPDATE` en SQL Server)."""

    async def list_active(self) -> list[Market]:
        """Mercados con `active=1`, ordenados por código."""
        ...

    async def get_by_code(self, code: str) -> Market | None:
        """Mercado por su código (`15011501`, `CIUDADES`…)."""
        ...


class PriceRepository(GenericRepository[MarketPrice], Protocol):
    """Precios en `BM_MarketPrice` (todos los mercados) y `BM_CatalogPrice` (solo 15011501). Nunca borra filas."""

    async def upsert(self, prices: pl.DataFrame) -> UpsertResult:
        """Inserta o actualiza en `BM_MarketPrice` por su llave única, dentro de la transacción de la sesión.

        Args:
            prices: Filas con `UPSERT_SCHEMA`, una por llave.

        Raises:
            ValueError: Si falta una columna, una columna de la llave viene nula o hay llaves repetidas.
        """
        ...

    async def upsert_report(self, prices: pl.DataFrame) -> UpsertResult:
        """Inserta o actualiza en `BM_CatalogPrice` por `REPORT_KEY` (se ignora `id_market`), en la misma transacción.

        Solo se llama con filas de `REPORT_MARKET_CODE`.

        Args:
            prices: Filas con `UPSERT_SCHEMA`, una por `REPORT_KEY`.

        Raises:
            ValueError: Si falta una columna, una columna de la llave viene nula o hay llaves repetidas.
        """
        ...
