"""Contrato de acceso al portal SISAP (HTTP). No usa ninguna base de datos."""

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.modules.midagri.model.sisap import FetchResult, SisapGenre, SisapMarket, SisapSource, SisapVariety


class SisapRepository(Protocol):
    """Portal SISAP de MIDAGRI: mercados, géneros, variedades con código y precios."""

    async def list_markets(self) -> list[SisapMarket]:
        """Mercados del portal mayorista (selector `#mercado`), para validar `BM_Market`."""
        ...

    async def list_genres(self, source: SisapSource, market_code: str) -> list[SisapGenre]:
        """Géneros de un mercado mayorista, o de todas las regiones si `source="CIUDADES"`."""
        ...

    async def list_varieties(self, source: SisapSource, genre_code: str) -> list[SisapVariety]:
        """Variedades de un género, con su código de 6 dígitos."""
        ...

    async def fetch_prices(
        self,
        source: SisapSource,
        market_code: str,
        varieties: Sequence[SisapVariety],
        date_from: date,
        date_to: date,
    ) -> FetchResult:
        """Precios de las variedades en el rango, en lotes concurrentes.

        Cada fila sale con `variety_code`, mapeado por nombre **dentro de las variedades de su lote**.
        Un lote que falla tras los reintentos queda en `FetchResult.errors` y no aborta a los demás.
        """
        ...
