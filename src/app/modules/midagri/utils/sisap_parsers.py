"""Parsers del HTML del portal SISAP (funciones puras, sin I/O).

pandas solo se usa para `read_html` y no sale de este módulo: las tablas de precios se devuelven
como `pl.DataFrame`. Portado de `system/network/downloader.py`, con estas diferencias:

- Los números se leen como `Decimal` exacto (el legado usaba `float`).
- Un mensaje de error del portal se distingue de "no hay resultados" (el legado devolvía vacío en ambos).
- Mercados, géneros y variedades se leen del HTML con lxml (el legado no los leía).

Formas de tabla verificadas contra el portal el 2026-09-24 (fixtures en `tests/fixtures/sisap/`):

- Mayorista, intervalo: fila 0 = variedad (colspan 3), fila 1 = Máximo/Promedio/Mínimo; cuerpo = fecha.
- Mayorista, día: columnas Producto (género) | Variedad | Máximo | Promedio | Mínimo; fecha en el `<h1>`.
- Ciudades, intervalo: filas 0–3 = región | variedad | Unidad/Equiv./Mayorista | min/prom/max; cuerpo = fecha.
- Ciudades, día: filas 1–3 = región | Unidad/Equiv./Mayorista | min/prom/max; columna 0 = variedad.
"""

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
import polars as pl
from lxml import html as lxml_html

from app.modules.midagri.model.sisap import SisapGenre, SisapMarket
from app.modules.midagri.utils.text import norm_text

MAYORISTA_REGION = "Lima Metropolitana"
"""Región de todos los precios del portal mayorista (se resuelve al distrito Lima, 1514)."""

MAYORISTA_UNIT = "Kg"
"""Unidad de los precios mayoristas de productos agrícolas (el legado usaba la misma)."""

PARSED_SCHEMA: dict[str, pl.DataType] = {
    "variety_name": pl.String(),
    "date": pl.Date(),
    "region": pl.String(),
    "unit": pl.String(),
    "equivalence": pl.Decimal(18, 4),
    "min": pl.Decimal(18, 4),
    "mean": pl.Decimal(18, 4),
    "max": pl.Decimal(18, 4),
}
"""Salida de los parsers de precios: una fila por variedad, fecha, región, unidad y equivalencia."""

_KEY = ["variety_name", "date", "region", "unit", "equivalence"]
_PRICE_FIELDS = ("min", "mean", "max")
_NO_RESULTS_MARKERS = (
    "noexistenresultados",  # Mayorista y Ciudades
    "elsistemasugiereparaestereporte",  # Ciudades, variedad sin ningún precio en el rango
)
_QUERY_TOO_LARGE_MARKER = "sehaexcedidoeltiempolimite"
_DATE_IN_TITLE = re.compile(r"Fecha:\s*(\d{2}/\d{2}/\d{4})")
_ERROR_MESSAGE = re.compile(r"<p class=['\"]?mensajeDeError['\"]?>(.*?)</p>", re.S | re.I)
_NUMBER_IN_TEXT = re.compile(r"-?\d+(?:[.,]\d+)*")


class SisapResponseError(ValueError):
    """El portal respondió con un mensaje de error o con un HTML que no tiene la forma esperada."""


class SisapQueryTooLargeError(SisapResponseError):
    """El portal agotó su tiempo de consulta y pide "reducir la cantidad de criterios".

    Depende de la carga del servidor: el mismo lote puede responder bien minutos después. El repositorio
    lo resuelve partiendo el lote (menos variedades o menos días).
    """


# --- Selectores y listas (lxml) -------------------------------------------------------------


def parse_markets(page_html: str) -> list[SisapMarket]:
    """Mercados del selector `#mercado` de la página de consulta mayorista (sin la opción `*`)."""
    document = lxml_html.fromstring(page_html)
    return [
        SisapMarket(code=option.get("value", "").strip(), name=option.text_content().strip())
        for option in document.xpath("//select[@id='mercado']//option")
        if option.get("value", "*").strip() not in ("", "*")
    ]


def parse_checkbox_items(fragment_html: str) -> list[tuple[str, str]]:
    """Pares `(código, nombre)` de los checkbox `productos[]` (géneros o variedades).

    Returns:
        Lista en el orden del portal. Vacía si el fragmento no trae checkbox.
    """
    if not fragment_html.strip():
        return []
    document = lxml_html.fromstring(f"<div>{fragment_html}</div>")
    items: list[tuple[str, str]] = []
    for checkbox in document.xpath("//input[@name='productos[]']"):
        code = (checkbox.get("value") or "").strip()
        label = checkbox.getparent()
        name = " ".join(label.text_content().split()) if label is not None else ""
        if code and code != "NA" and name:
            items.append((code, name))
    return items


def parse_genres(fragment_html: str) -> list[SisapGenre]:
    """Géneros (cultivos padre) de `generos/filtrarPorMercado` o `generos/filtrarPorRegion`."""
    return [SisapGenre(code=code, name=name) for code, name in parse_checkbox_items(fragment_html)]


# --- Tablas de precios ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Column:
    """Qué contiene una columna de la tabla de precios, deducido de sus filas de cabecera."""

    index: int
    field: str  # "unit" | "equivalence" | "min" | "mean" | "max"
    region: str | None
    variety: str | None


def parse_mayorista_prices(page_html: str) -> pl.DataFrame:
    """Precios de `mayorista/resumenes/filtrar` (intervalo o día).

    Raises:
        SisapResponseError: Si el portal devolvió un mensaje de error distinto de "no hay resultados".
    """
    grid = _read_grid(page_html)
    if grid is None:
        return _empty()
    header_rows = _count_header_rows(grid)
    if norm_text(grid[0][1] if len(grid[0]) > 1 else "") == "variedad":
        return _mayorista_day(grid, _title_date(page_html))
    if header_rows != 2:
        raise SisapResponseError(f"Tabla mayorista con {header_rows} filas de cabecera; se esperaban 2.")
    columns = [
        _Column(index=i, field=field, region=MAYORISTA_REGION, variety=grid[0][i])
        for i in range(1, len(grid[0]))
        if (field := _field_of(grid[1][i])) in _PRICE_FIELDS
    ]
    records = _records_by_date(grid[header_rows:], columns, variety_from_body=False)
    return _finish(records, default_unit=MAYORISTA_UNIT)


def parse_ciudades_prices(page_html: str) -> pl.DataFrame:
    """Precios de `ciudades/resumenes/filtrar` (intervalo o día), por región.

    Raises:
        SisapResponseError: Si el portal devolvió un mensaje de error distinto de "no hay resultados".
    """
    grid = _read_grid(page_html)
    if grid is None:
        return _empty()
    header_rows = _count_header_rows(grid)
    if header_rows != 4:
        raise SisapResponseError(f"Tabla de ciudades con {header_rows} filas de cabecera; se esperaban 4.")
    first = norm_text(grid[0][0])
    if first == "fecha":
        columns = [
            _Column(index=i, field=field, region=grid[0][i], variety=grid[1][i])
            for i in range(1, len(grid[0]))
            if (field := _field_of(grid[3][i] or grid[2][i]))
        ]
        records = _records_by_date(grid[header_rows:], columns, variety_from_body=False)
    elif first == "productos":
        day = _title_date(page_html)
        columns = [
            _Column(index=i, field=field, region=grid[1][i], variety=None)
            for i in range(1, len(grid[1]))
            if (field := _field_of(grid[3][i] or grid[2][i]))
        ]
        records = _records_for_day(grid[header_rows:], columns, day)
    else:
        raise SisapResponseError(f"Tabla de ciudades con primera columna inesperada: {grid[0][0]!r}.")
    return _finish(records, default_unit=None)


def _mayorista_day(grid: list[list[str]], day: date) -> pl.DataFrame:
    columns = [
        _Column(index=i, field=field, region=MAYORISTA_REGION, variety=None)
        for i in range(2, len(grid[0]))
        if (field := _field_of(grid[0][i])) in _PRICE_FIELDS
    ]
    # La columna 0 es el género (con rowspan); la variedad está en la 1. `_records_for_day` lee la variedad de
    # la columna 0, así que se reemplaza el género por la variedad sin mover los índices de las demás columnas.
    body = [[row[1], *row[1:]] for row in grid[1:] if norm_text(row[1]) not in ("", "variedad")]
    return _finish(_records_for_day(body, columns, day), default_unit=MAYORISTA_UNIT)


def _records_by_date(body: list[list[str]], columns: list[_Column], *, variety_from_body: bool) -> list[dict]:
    """Una fila de cuerpo por fecha; agrupa las columnas por (región, variedad)."""
    records: list[dict] = []
    for row in body:
        day = _parse_date(row[0])
        if day is None:
            continue
        records.extend(_group_columns(row, columns, day, variety=row[0] if variety_from_body else None))
    return records


def _records_for_day(body: list[list[str]], columns: list[_Column], day: date) -> list[dict]:
    """Una fila de cuerpo por variedad (columna 0); una sola fecha para toda la tabla."""
    records: list[dict] = []
    for row in body:
        if row[0]:
            records.extend(_group_columns(row, columns, day, variety=row[0]))
    return records


def _group_columns(row: list[str], columns: list[_Column], day: date, *, variety: str | None) -> Iterable[dict]:
    blocks: dict[tuple[str | None, str | None], dict] = {}
    for column in columns:
        name = variety if variety is not None else column.variety
        block = blocks.setdefault((column.region, name), {"variety_name": name, "date": day, "region": column.region})
        cell = row[column.index] if column.index < len(row) else ""
        if column.field == "unit":
            block["unit"] = cell or None
        elif column.field == "equivalence":
            block["equivalence"] = _parse_number(cell, first_number=True)
        else:
            block[column.field] = _parse_number(cell)
    return blocks.values()


def _finish(records: list[dict], *, default_unit: str | None) -> pl.DataFrame:
    if not records:
        return _empty()
    frame = pl.DataFrame(records, schema_overrides=PARSED_SCHEMA, infer_schema_length=None)
    for column, dtype in PARSED_SCHEMA.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None, dtype=dtype).alias(column))
    if default_unit is not None:
        frame = frame.with_columns(pl.col("unit").fill_null(default_unit))
    return (
        frame.select(list(PARSED_SCHEMA))
        .with_columns(pl.col("variety_name").str.strip_chars(), pl.col("region").str.strip_chars())
        .filter(pl.any_horizontal(pl.col(*_PRICE_FIELDS).is_not_null()))
        .group_by(_KEY)
        .agg(pl.col(*_PRICE_FIELDS).max())
        .sort(_KEY, nulls_last=True)
        .select(list(PARSED_SCHEMA))
    )


def _empty() -> pl.DataFrame:
    return pl.DataFrame(schema=PARSED_SCHEMA)


# --- Helpers de celdas ----------------------------------------------------------------------


def _read_grid(page_html: str) -> list[list[str]] | None:
    """Primera tabla como matriz de textos, o `None` si el portal dice que no hay resultados."""
    message = _ERROR_MESSAGE.search(page_html)
    if message:
        text = " ".join(lxml_html.fromstring(f"<p>{message.group(1)}</p>").text_content().split())
        key = norm_text(text)
        if any(marker in key for marker in _NO_RESULTS_MARKERS):
            return None
        if _QUERY_TOO_LARGE_MARKER in key:
            raise SisapQueryTooLargeError(f"El portal SISAP respondió: {text}")
        raise SisapResponseError(f"El portal SISAP respondió: {text}")
    if "<table" not in page_html.lower():
        raise SisapResponseError("La respuesta del portal SISAP no trae tabla ni mensaje.")
    frame = pd.read_html(io.StringIO(page_html), header=None, keep_default_na=False, thousands=None)[0]
    return [[" ".join(str(cell).split()) for cell in row] for row in frame.astype(str).to_numpy().tolist()]


def _count_header_rows(grid: list[list[str]]) -> int:
    """Filas de cabecera: las primeras que repiten la celda (0, 0) por el `rowspan` ("Fecha", "Productos")."""
    first = grid[0][0]
    count = 0
    for row in grid:
        if row[0] != first:
            break
        count += 1
    return count


def _field_of(label: str) -> str | None:
    """Tipo de columna según su cabecera: unidad, equivalencia o precio mínimo/promedio/máximo."""
    key = norm_text(label)
    if key.startswith("unidad"):
        return "unit"
    if key.startswith("equiv"):
        return "equivalence"
    if "prom" in key:
        return "mean"
    if "max" in key:
        return "max"
    if "min" in key:
        return "min"
    return None


def _parse_number(cell: str, *, first_number: bool = False) -> Decimal | None:
    """Número del portal como `Decimal` exacto. Acepta `1234.50`, `1,234.50` y `1.234,50`.

    Args:
        cell: Texto de la celda.
        first_number: Si es True, toma el primer número dentro del texto (p. ej. `"25 kg"`).
    """
    text = cell.replace("\xa0", "").strip()
    if first_number:
        match = _NUMBER_IN_TEXT.search(text)
        text = match.group(0) if match else ""
    text = text.replace(" ", "")
    if not text or text in {"-", "--"}:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _parse_date(cell: str) -> date | None:
    try:
        return datetime.strptime(cell.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _title_date(page_html: str) -> date:
    """Fecha de un reporte de un solo día, tomada del `<h1>Fecha: dd/mm/aaaa</h1>`."""
    match = _DATE_IN_TITLE.search(page_html)
    day = _parse_date(match.group(1)) if match else None
    if day is None:
        raise SisapResponseError("El reporte de un día no trae la fecha en el título.")
    return day
