"""Acceso al portal SISAP con HTTPX asíncrono.

Endpoints verificados el 2026-09-24:

| Qué | Mayorista | Ciudades |
|---|---|---|
| Mercados | `GET mayorista/resumenes/consultar/` (`#mercado`) | — |
| Géneros | `POST mayorista/generos/filtrarPorMercado` `mercado=<código>` | `POST ciudades/generos/filtrarPorRegion` `region=*` |
| Variedades | `POST mayorista/variedades/filtrarPorGenero` `expandir=<género>~checkBox` | `POST ciudades/…` (igual) |
| Precios | **`POST`** `mayorista/resumenes/filtrar` | **`GET`** `ciudades/resumenes/filtrar` (con POST ignora los parámetros) |
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import date, timedelta
from itertools import batched, groupby

import httpx
import polars as pl
from asyncer import asyncify

from app.modules.midagri.model.sisap import (
    CIUDADES_MARKET_CODE,
    PRICE_SCHEMA,
    FetchError,
    FetchResult,
    SisapGenre,
    SisapMarket,
    SisapSource,
    SisapVariety,
)
from app.modules.midagri.repository.interface.sisap_repository import SisapRepository
from app.modules.midagri.utils.sisap_parsers import (
    SisapQueryTooLargeError,
    SisapResponseError,
    parse_checkbox_items,
    parse_ciudades_prices,
    parse_genres,
    parse_markets,
    parse_mayorista_prices,
)
from app.modules.midagri.utils.text import norm_key, norm_text

logger = logging.getLogger(__name__)

BATCH_SIZE = 20
"""Variedades por consulta de precios (los rangos largos con muchos productos son muy lentos)."""

DEFAULT_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (ETL SISAP-MIDAGRI)",
}

_PRICE_VARIABLES: dict[SisapSource, list[str]] = {
    "MAYORISTA": ["precio_max", "precio_prom", "precio_min"],
    "CIUDADES": ["may_precio_min", "may_precio_prom", "may_precio_max"],
}

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class SisapRepositoryImpl(SisapRepository):
    """Cliente del portal SISAP.

    Recibe un `httpx.AsyncClient` con `base_url` apuntando a `.../sisap/portal2/` y no lo cierra: el dueño
    del cliente (la dependencia o el service del ETL) lo abre y lo cierra.

    Args:
        client: Cliente HTTP compartido por todas las consultas de una ejecución.
        concurrency: Solicitudes simultáneas al portal como máximo (todas, no solo las de precios).
        retries: Reintentos por consulta ante errores de red o respuestas 5xx.
        backoff_seconds: Espera base entre reintentos (se duplica en cada intento).
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        concurrency: int = 4,
        retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.client = client
        self._semaphore = asyncio.Semaphore(concurrency)
        self._retries = retries
        self._backoff_seconds = backoff_seconds

    # --- Catálogos del portal ---------------------------------------------------------------

    async def list_markets(self) -> list[SisapMarket]:
        page = await self._send(lambda: self.client.get("mayorista/resumenes/consultar/"))
        return parse_markets(page)

    async def list_genres(self, source: SisapSource, market_code: str) -> list[SisapGenre]:
        if source == "MAYORISTA":
            page = await self._send(
                lambda: self.client.post("mayorista/generos/filtrarPorMercado", data={"mercado": market_code})
            )
        else:
            page = await self._send(lambda: self.client.post("ciudades/generos/filtrarPorRegion", data={"region": "*"}))
        return parse_genres(page)

    async def list_varieties(self, source: SisapSource, genre_code: str) -> list[SisapVariety]:
        page = await self._send(
            lambda: self.client.post(
                f"{_path(source)}/variedades/filtrarPorGenero", data={"expandir": f"{genre_code}~checkBox"}
            )
        )
        return [SisapVariety(code=code, name=name, genre_code=genre_code) for code, name in parse_checkbox_items(page)]

    # --- Precios ----------------------------------------------------------------------------

    async def fetch_prices(
        self,
        source: SisapSource,
        market_code: str,
        varieties: Sequence[SisapVariety],
        date_from: date,
        date_to: date,
    ) -> FetchResult:
        if date_from > date_to:
            raise ValueError(f"'date_from' ({date_from}) no puede ser posterior a 'date_to' ({date_to})")
        batches = _batches(varieties)
        windows = _monthly_windows(date_from, date_to) if source == "CIUDADES" else [(date_from, date_to)]
        jobs = [(batch, start, end) for batch in batches for start, end in windows]
        logger.info(
            "SISAP %s %s: %s variedades en %s consultas (%s → %s)",
            source,
            market_code,
            len(varieties),
            len(jobs),
            date_from,
            date_to,
        )
        outcomes = await asyncio.gather(
            *(self._fetch_batch(source, market_code, batch, start, end) for batch, start, end in jobs)
        )
        frames = [frame for batch_frames, _ in outcomes for frame in batch_frames]
        errors = [error for _, batch_errors in outcomes for error in batch_errors]
        rows = pl.concat(frames, how="vertical") if frames else pl.DataFrame(schema=PRICE_SCHEMA)
        return FetchResult(rows=rows.sort("variety_code", "date", "region", nulls_last=True), errors=errors)

    async def _fetch_batch(
        self,
        source: SisapSource,
        market_code: str,
        batch: tuple[SisapVariety, ...],
        date_from: date,
        date_to: date,
    ) -> tuple[list[pl.DataFrame], list[FetchError]]:
        """Descarga un lote. Si el portal pide "reducir criterios", lo parte en dos y vuelve a intentar.

        Primero parte las variedades; con una sola variedad, parte el rango de fechas. Un lote de una
        variedad y un día que igual agota el tiempo queda como error.
        """
        codes = tuple(variety.code for variety in batch)
        params = _price_params(source, market_code, codes, date_from, date_to)
        try:
            if source == "MAYORISTA":
                page = await self._send(lambda: self.client.post("mayorista/resumenes/filtrar", data=params))
            else:
                page = await self._send(lambda: self.client.get("ciudades/resumenes/filtrar", params=params))
            parser = parse_mayorista_prices if source == "MAYORISTA" else parse_ciudades_prices
            parsed = await asyncify(parser)(page)
        except SisapQueryTooLargeError as error:
            halves = _split(batch, date_from, date_to)
            if halves is None:
                return [], [self._error(source, market_code, codes, date_from, date_to, error)]
            logger.info(
                "SISAP %s %s: consulta muy grande (%s, %s → %s); se parte en dos",
                source,
                market_code,
                codes,
                date_from,
                date_to,
            )
            parts = await asyncio.gather(*(self._fetch_batch(source, market_code, *half) for half in halves))
            return [frame for frames, _ in parts for frame in frames], [
                error for _, errors in parts for error in errors
            ]
        except (*_RETRYABLE, SisapResponseError) as error:
            return [], [self._error(source, market_code, codes, date_from, date_to, error)]
        return [_with_codes(parsed, batch, market_code)], []

    @staticmethod
    def _error(
        source: SisapSource, market_code: str, codes: tuple[str, ...], date_from: date, date_to: date, error: Exception
    ) -> FetchError:
        logger.warning("SISAP %s %s: lote %s falló: %s", source, market_code, codes, error)
        return FetchError(market_code, codes, date_from, date_to, f"{type(error).__name__}: {error}")

    # --- HTTP -------------------------------------------------------------------------------

    async def _send(self, request: Callable[[], Awaitable[httpx.Response]]) -> str:
        """Envía con reintentos ante errores de red o 5xx y devuelve el cuerpo decodificado (latin-1)."""
        for attempt in range(self._retries + 1):
            try:
                async with self._semaphore:  # a lo sumo `concurrency` solicitudes al portal a la vez
                    response = await request()
                response.raise_for_status()
                return response.content.decode("latin-1")
            except httpx.HTTPStatusError as error:
                if error.response.status_code < 500 or attempt == self._retries:
                    raise
                last_error: Exception = error
            except httpx.TransportError as error:
                if attempt == self._retries:
                    raise
                last_error = error
            delay = self._backoff_seconds * 2**attempt
            logger.info("SISAP: reintento %s/%s en %.1fs (%s)", attempt + 1, self._retries, delay, last_error)
            await asyncio.sleep(delay)
        raise AssertionError("inalcanzable")  # pragma: no cover


def build_sisap_client(
    base_url: str, timeout_seconds: float, *, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """Cliente HTTP para el portal (`base_url` = `.../sisap/portal2`). `transport` solo se usa en pruebas."""
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/") + "/",
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=True,
        transport=transport,
    )


def _path(source: SisapSource) -> str:
    return "mayorista" if source == "MAYORISTA" else "ciudades"


def _price_params(
    source: SisapSource, market_code: str, codes: Sequence[str], date_from: date, date_to: date
) -> dict[str, str | list[str]]:
    hasta = date_to.strftime("%d/%m/%Y")
    params: dict[str, str | list[str]] = {
        "variables[]": _PRICE_VARIABLES[source],
        "fecha": hasta,
        "desde": date_from.strftime("%d/%m/%Y"),
        "hasta": hasta,
        "anios[]": date_to.strftime("%Y"),
        "meses[]": date_to.strftime("%m"),
        "productos[]": list(codes),
        "periodicidad": "dia" if date_from == date_to else "intervalo",
        "__ajax_carga_final": "consulta",
        "ajax": "true",
    }
    if source == "MAYORISTA":
        params["mercado"] = market_code
    else:
        params["region"] = "*"
    return params


def _batches(varieties: Sequence[SisapVariety]) -> list[tuple[SisapVariety, ...]]:
    """Lotes de `BATCH_SIZE` variedades **del mismo género**, para que los nombres no choquen en el mapeo."""
    ordered = sorted(varieties, key=lambda variety: (variety.genre_code, variety.code))
    return [
        batch
        for _, same_genre in groupby(ordered, key=lambda variety: variety.genre_code)
        for batch in batched(same_genre, BATCH_SIZE, strict=False)
    ]


def _split(
    batch: tuple[SisapVariety, ...], date_from: date, date_to: date
) -> list[tuple[tuple[SisapVariety, ...], date, date]] | None:
    """Parte una consulta en dos: primero por variedades y, con una sola, por fechas. `None` si ya es mínima."""
    if len(batch) > 1:
        middle = len(batch) // 2
        return [(batch[:middle], date_from, date_to), (batch[middle:], date_from, date_to)]
    if date_from < date_to:
        middle_day = date_from + (date_to - date_from) // 2
        return [(batch, date_from, middle_day), (batch, middle_day + timedelta(days=1), date_to)]
    return None


def _monthly_windows(date_from: date, date_to: date) -> list[tuple[date, date]]:
    """Parte el rango en ventanas de un mes calendario (Ciudades es muy lento con rangos largos)."""
    windows: list[tuple[date, date]] = []
    start = date_from
    while start <= date_to:
        next_month = (start.replace(day=1) + timedelta(days=32)).replace(day=1)
        end = min(date_to, next_month - timedelta(days=1))
        windows.append((start, end))
        start = end + timedelta(days=1)
    return windows


def _with_codes(parsed: pl.DataFrame, batch: Sequence[SisapVariety], market_code: str) -> pl.DataFrame:
    """Agrega `variety_code` mapeando el nombre normalizado **dentro del lote**, y el mercado."""
    by_key: dict[str, str | None] = {}
    for variety in batch:
        key = norm_text(variety.name)
        by_key[key] = None if key in by_key else variety.code  # nombre repetido en el lote: no se adivina
    mapping = pl.DataFrame(
        {"key": list(by_key), "variety_code": list(by_key.values())},
        schema={"key": pl.String, "variety_code": pl.String},
    )
    market = market_code if market_code else CIUDADES_MARKET_CODE
    return (
        parsed.with_columns(key=norm_key("variety_name"))
        .join(mapping, on="key", how="left")
        .with_columns(market_code=pl.lit(market))
        .select(list(PRICE_SCHEMA))
    )
