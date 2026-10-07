"""Valores del portal SISAP que maneja la capa de repositorio (no son DTOs de la API ni tablas)."""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import polars as pl

SisapSource = Literal["MAYORISTA", "CIUDADES"]
"""Portal de origen: mercados mayoristas de Lima (`mayorista/…`) o el nacional por región (`ciudades/…`)."""

CIUDADES_MARKET_CODE = "CIUDADES"
"""Código de mercado con el que se registran los precios del portal Ciudades (`BM_Market.code`)."""

PRICE_SCHEMA: dict[str, pl.DataType] = {
    "market_code": pl.String(),
    "variety_code": pl.String(),
    "variety_name": pl.String(),
    "date": pl.Date(),
    "region": pl.String(),
    "unit": pl.String(),
    "equivalence": pl.Decimal(18, 4),
    "min": pl.Decimal(18, 4),
    "mean": pl.Decimal(18, 4),
    "max": pl.Decimal(18, 4),
}
"""Columnas de un precio descargado. `variety_code` es nulo si el nombre no se pudo mapear en su lote."""


@dataclass(frozen=True, slots=True)
class SisapMarket:
    """Mercado del selector `#mercado` del portal mayorista."""

    code: str
    name: str


@dataclass(frozen=True, slots=True)
class MarketRef:
    """Mercado a consultar: portal de origen, código (`BM_Market.code`) y nombre para mostrar."""

    source: SisapSource
    code: str
    name: str

    @property
    def label(self) -> str:
        """Nombre con el que aparece en el Excel y en los correos."""
        return "Portal Ciudades" if self.source == "CIUDADES" else f"{self.name} ({self.code})"


@dataclass(frozen=True, slots=True)
class SisapGenre:
    """Cultivo padre (género) publicado por el portal, con su código de 4 dígitos."""

    code: str
    name: str


@dataclass(frozen=True, slots=True)
class SisapVariety:
    """Variedad publicada por el portal, con su código de 6 dígitos (el mismo de `BM_Catalog.code`)."""

    code: str
    name: str
    genre_code: str


@dataclass(frozen=True, slots=True)
class FetchError:
    """Lote que no se pudo descargar o interpretar."""

    market_code: str
    variety_codes: tuple[str, ...]
    date_from: date
    date_to: date
    message: str


@dataclass(slots=True)
class FetchResult:
    """Precios descargados de un mercado y los lotes que fallaron (fallo parcial, no aborta)."""

    rows: pl.DataFrame = field(default_factory=lambda: pl.DataFrame(schema=PRICE_SCHEMA))
    errors: list[FetchError] = field(default_factory=list)
