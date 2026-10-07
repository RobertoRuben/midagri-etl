"""Reporte de faltantes del catálogo (ESC1/ESC2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

GapStatus = Literal["ESC1", "ESC2"]


class GapPriceResponse(BaseModel):
    """Precio de un faltante en un mercado: el del último día con precio válido, en S/ por kg.

    En Ciudades, `mean` es el promedio de las regiones ese día; `min` y `max`, el menor y el mayor.
    """

    market: str
    price_date: date | None = None
    min: Decimal | None = None
    mean: Decimal | None = None
    max: Decimal | None = None


class GapItemResponse(BaseModel):
    """Variedad publicada con precio en el periodo que no está en `BM_Catalog`."""

    status: GapStatus
    variety_code: str
    variety_name: str
    crop_code: str
    crop_name: str
    markets: list[str]
    last_price_date: date
    prices: list[GapPriceResponse] = []
    """Un precio por mercado. Vacío en los reportes anteriores al 2026-09-25."""


class GapReportResponse(BaseModel):
    """Faltantes bajo cultivos activos (ESC2) o inexistentes en la multi gestión (ESC1).

    Attributes:
        warnings: Consultas al portal que fallaron: si no está vacío, el reporte puede estar incompleto.
    """

    generated_at: datetime
    date_from: date
    date_to: date
    markets: list[str]
    items: list[GapItemResponse]
    total_esc1: int
    total_esc2: int
    warnings: list[str] = []
