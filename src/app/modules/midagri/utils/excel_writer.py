"""Excel de faltantes (D31, D33, D34), con xlsxwriter. Un solo archivo, el que se adjunta al correo de fin.

- Hoja `Faltantes`: informativa; una fila por producto que no se cargó y mercado donde se publicó, con su código y
  el precio del último día (mínimo, promedio y máximo en S/ por kg; en Ciudades, de las regiones) (`COLUMNS`).
- Hoja `Cultivos`: se sube; los cultivos que faltan en la multi gestión (ESC1), que se crean primero.
- Hoja `Registro`: se sube a `POST /catalog/registrations`; los productos faltantes, en el formato del catálogo
  del app (`utils/registration_sheet.py`).
- Hoja `Avisos`: solo si alguna consulta al portal falló (la lista puede estar incompleta).
"""

import io
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import xlsxwriter
from xlsxwriter.format import Format
from xlsxwriter.worksheet import Worksheet

from app.modules.midagri.dto.response.gap_report_response import GapItemResponse, GapReportResponse
from app.modules.midagri.utils.registration_sheet import (
    CROP_HEADERS,
    CROP_SHEET,
    REGISTRATION_HEADERS,
    REGISTRATION_SHEET,
    crop_rows,
    registration_rows,
    sentence_case,
)

SHEET = "Faltantes"
WARNINGS_SHEET = "Avisos"
EMPTY_MESSAGE = "(sin productos faltantes en el periodo)"
OBSERVATIONS: dict[str, str] = {
    "ESC1": "Falta el producto y su cultivo",
    "ESC2": "Falta el producto",
}
"""Texto de la columna `Observación` según el escenario (D2, D14)."""


@dataclass(frozen=True, slots=True)
class _Column:
    header: str
    width: float


COLUMNS: tuple[_Column, ...] = (
    _Column("Código", 10),
    _Column("Producto", 34),
    _Column("Cultivo", 22),
    _Column("Mercado", 36),
    _Column("Fecha del precio", 12),
    _Column("Precio mín. (S/ x kg)", 12),
    _Column("Precio prom. (S/ x kg)", 12),
    _Column("Precio máx. (S/ x kg)", 12),
    _Column("Observación", 30),
)

Cell = str | Decimal | None
REGISTRATION_WIDTHS: tuple[float, ...] = (10, 18, 26, 34, 12, 10, 10, 10)
CROP_WIDTHS: tuple[float, ...] = (10, 34, 10)

__all__ = ["COLUMNS", "build_gap_workbook", "gap_excel_filename", "sentence_case"]


def gap_excel_filename(report: GapReportResponse) -> str:
    """`faltantes_sisap_<desde>_<hasta>.xlsx`."""
    return f"faltantes_sisap_{report.date_from:%Y%m%d}_{report.date_to:%Y%m%d}.xlsx"


def build_gap_workbook(report: GapReportResponse) -> bytes:
    """Arma el Excel del reporte y devuelve sus bytes."""
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    header = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#2F5597", "border": 1})
    header.set_text_wrap()
    text = workbook.add_format({"num_format": "@"})  # conserva los ceros a la izquierda del código
    money = workbook.add_format({"num_format": "0.00"})

    rows = [row for item in report.items for row in _rows(item)]
    _write_table(
        workbook.add_worksheet(SHEET),
        header,
        text,
        money,
        [(column.header, column.width) for column in COLUMNS],
        rows,
        empty=EMPTY_MESSAGE,
    )
    _write_table(
        workbook.add_worksheet(CROP_SHEET),
        header,
        text,
        money,
        list(zip(CROP_HEADERS, CROP_WIDTHS, strict=True)),
        crop_rows(report.items),
    )
    _write_table(
        workbook.add_worksheet(REGISTRATION_SHEET),
        header,
        text,
        money,
        list(zip(REGISTRATION_HEADERS, REGISTRATION_WIDTHS, strict=True)),
        registration_rows(report.items),
    )
    if report.warnings:
        _write_warnings(workbook.add_worksheet(WARNINGS_SHEET), header, report.warnings)
    workbook.close()
    return buffer.getvalue()


def _rows(item: GapItemResponse) -> list[list[Cell]]:
    """Una fila por mercado. Sin precio calculado (reportes anteriores), solo el mercado y la última fecha."""
    head: list[Cell] = [item.variety_code, sentence_case(item.variety_name), item.crop_name]
    observation = OBSERVATIONS[item.status]
    if not item.prices:
        last = f"{item.last_price_date:%d/%m/%Y}"
        return [[*head, market, last, None, None, None, observation] for market in item.markets]
    return [
        [
            *head,
            price.market,
            f"{price.price_date:%d/%m/%Y}" if price.price_date else None,
            price.min,
            price.mean,
            price.max,
            observation,
        ]
        for price in item.prices
    ]


def _write_table(
    sheet: Worksheet,
    header: Format,
    text: Format,
    money: Format,
    columns: Sequence[tuple[str, float]],
    rows: Sequence[Sequence[Cell]],
    *,
    empty: str | None = None,
) -> None:
    """Encabezado fijo, texto (códigos con ceros), precios como número y autofiltro. `empty` si no hay filas."""
    for index, (title, width) in enumerate(columns):
        sheet.write_string(0, index, title, header)
        sheet.set_column(index, index, width, text)
    for row_index, row in enumerate(rows, start=1):
        for column_index, value in enumerate(row):
            if isinstance(value, Decimal):
                sheet.write_number(row_index, column_index, float(value), money)
            elif value:
                sheet.write_string(row_index, column_index, value, text)
            else:
                sheet.write_blank(row_index, column_index, None, text)
    if not rows and empty:
        sheet.write_string(1, 1, empty)
    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, max(len(rows), 1), len(columns) - 1)


def _write_warnings(sheet: Worksheet, header: Format, warnings: Sequence[str]) -> None:
    sheet.set_column(0, 0, 120)
    sheet.write_string(0, 0, "Consultas al portal que fallaron: la lista de faltantes puede estar incompleta", header)
    for row, warning in enumerate(warnings, start=1):
        sheet.write_string(row, 0, warning)
