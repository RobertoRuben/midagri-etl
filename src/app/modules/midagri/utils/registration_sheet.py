"""Hojas `Cultivos` y `Registro` del Excel de faltantes (D33, D34): se arman para el correo y se leen al subirlas.

- `Cultivos` (`CROP_HEADERS`): cultivos que faltan en la multi gestión (ESC1). Se crean antes que los productos.
- `Registro` (`REGISTRATION_HEADERS`, las columnas del catálogo del app): productos faltantes.

Todas las filas que queden en las hojas se registran; para no registrar una, se borra la fila. Funciones puras.
"""

import io
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

import polars as pl

from app.modules.midagri.dto.response.gap_report_response import GapItemResponse
from app.modules.midagri.utils.gap_classifier import is_agricultural
from app.modules.midagri.utils.text import norm_text

CROP_SHEET = "Cultivos"
CROP_HEADERS: tuple[str, ...] = ("Código", "Nombre", "Estado")
"""Cultivo de la multi gestión (`IT_Multivalor`, `BM_TCATCAT`): el resto de campos es fijo."""
CROP_CODE_LENGTH = 4
MAX_CROP_NAME = 50  # uspIT_GuardarActualizarMultivalores lee Nombre como VARCHAR(50)

REGISTRATION_SHEET = "Registro"
REGISTRATION_HEADERS: tuple[str, ...] = (
    "Código",
    "Tipo",
    "Categoria",
    "Nombre",
    "Und. Medida",
    "Cantidad",
    "Precio",
    "Estado",
)
"""Columnas del catálogo del app, en su orden y con su texto exacto."""

TYPE_LABEL = "Materias Primas"
"""`IT_Multivalor` `BM_TCATTY` del tipo `0001` (productos de mercado)."""
UNIT_KG = "KG"
STATUS_ACTIVE = "Activo"
MAX_NAME = 120  # uspBM_SaveUpdateCatalogo recorta @name a 120 caracteres
CODE_LENGTH = 6


@dataclass(slots=True)
class RegistrationRow:
    """Una fila de la hoja `Registro` o `Cultivos` ya leída y validada.

    Attributes:
        row_number: Número de fila en Excel (la 2 es la primera de datos).
        crop_code: Los 4 primeros dígitos del código (la `category` de `BM_Catalog`); en un cultivo, su código.
        errors: Motivos por los que no se puede registrar. Vacío = válida.
        warnings: Avisos que no impiden el registro (p. ej. `Precio` ignorado).
    """

    row_number: int
    code: str
    name: str
    crop_code: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def sentence_case(name: str) -> str:
    """Nombre en formato "Oración", como el catálogo: `"Hoja de coca Tingo María"` → `"Hoja de coca tingo maría"`."""
    clean = " ".join(name.split())
    return clean[:1].upper() + clean[1:].lower()


def crop_rows(items: Sequence[GapItemResponse]) -> list[list[str]]:
    """Filas de la hoja `Cultivos`: un cultivo por cada código ESC1 (no existe en la multi gestión), ordenados."""
    crops = {item.crop_code: item.crop_name for item in items if item.status == "ESC1"}
    return [[code, " ".join(name.split())[:MAX_CROP_NAME], STATUS_ACTIVE] for code, name in sorted(crops.items())]


def registration_rows(items: Sequence[GapItemResponse]) -> list[list[str]]:
    """Filas de la hoja `Registro`: todos los faltantes (ESC2 y, con su cultivo en `Cultivos`, ESC1)."""
    return [
        [
            item.variety_code,
            TYPE_LABEL,
            item.crop_name,
            sentence_case(item.variety_name)[:MAX_NAME],
            UNIT_KG,
            "",
            "",
            STATUS_ACTIVE,
        ]
        for item in items
    ]


def sheet_frame(rows: Sequence[Sequence[str]], headers: Sequence[str]) -> pl.DataFrame:
    """Filas armadas con `crop_rows` o `registration_rows` en el formato de `read_*_sheet`, sin pasar por Excel.

    Lo usa el alta automática del ETL (D36) para validar los faltantes con las mismas reglas que la subida.
    """
    return pl.DataFrame(
        [list(row) for row in rows], schema=dict.fromkeys(headers, pl.String), orient="row"
    ).with_row_index("row_number", offset=2)


def read_registration_sheet(content: bytes) -> pl.DataFrame:
    """Lee la hoja `Registro` como texto (conserva los ceros del código) y quita las filas vacías.

    Returns:
        Las columnas de `REGISTRATION_HEADERS` más `row_number` (fila de Excel).

    Raises:
        ValueError: Si el archivo no es un Excel válido, no tiene la hoja o sus encabezados no son los esperados.
    """
    if REGISTRATION_SHEET not in _sheet_names(content):
        raise ValueError(f"No se pudo leer la hoja '{REGISTRATION_SHEET}' del Excel: el archivo no la tiene")
    return _read_sheet(content, REGISTRATION_SHEET, REGISTRATION_HEADERS)


def read_crop_sheet(content: bytes) -> pl.DataFrame:
    """Lee la hoja `Cultivos` como texto. Es opcional: si el archivo no la tiene, devuelve una tabla vacía.

    Returns:
        Las columnas de `CROP_HEADERS` más `row_number`.

    Raises:
        ValueError: Si el archivo no es un Excel válido o la hoja tiene otros encabezados.
    """
    if CROP_SHEET not in _sheet_names(content):
        return pl.DataFrame(schema={"row_number": pl.UInt32, **dict.fromkeys(CROP_HEADERS, pl.String)})
    return _read_sheet(content, CROP_SHEET, CROP_HEADERS)


def _sheet_names(content: bytes) -> list[str]:
    try:
        return list(pl.read_excel(io.BytesIO(content), sheet_id=0, infer_schema_length=0).keys())
    except Exception as error:  # fastexcel lanza varios tipos según el problema (archivo, formato)
        raise ValueError(f"No se pudo leer el Excel: {error}") from error


def _read_sheet(content: bytes, sheet_name: str, expected: tuple[str, ...]) -> pl.DataFrame:
    try:
        # `drop_empty_rows=False`: las filas vacías se quitan abajo, sin correr el número de fila que ve el usuario.
        sheet = pl.read_excel(io.BytesIO(content), sheet_name=sheet_name, infer_schema_length=0, drop_empty_rows=False)
    except Exception as error:
        raise ValueError(f"No se pudo leer la hoja '{sheet_name}' del Excel: {error}") from error
    headers = [column.strip() for column in sheet.columns]
    if headers[: len(expected)] != list(expected):
        raise ValueError(
            f"La hoja '{sheet_name}' debe tener las columnas {', '.join(expected)} (en ese orden); "
            f"tiene: {', '.join(headers)}"
        )
    sheet = sheet.rename(dict(zip(sheet.columns, headers, strict=True))).select(expected)
    return (
        sheet.with_columns(pl.all().str.strip_chars())
        .with_row_index("row_number", offset=2)
        .filter(pl.any_horizontal(pl.col(expected).is_not_null() & (pl.col(expected) != "")))
    )


def validate_crops(sheet: pl.DataFrame, crops: Mapping[str, tuple[str, bool]]) -> list[RegistrationRow]:
    """Valida cada fila de la hoja `Cultivos` (D34).

    Args:
        sheet: Resultado de `read_crop_sheet`.
        crops: `código → (nombre, activo)` de los cultivos que ya existen (`BM_TCATCAT`, activos e inactivos).

    Returns:
        Una fila por cultivo. Uno que ya existe activo queda válido con aviso (el llamador lo omite); uno que existe
        inactivo es inválido: no se reactiva (D6).
    """
    rows: list[RegistrationRow] = []
    seen: dict[str, int] = {}
    for record in sheet.iter_rows(named=True):
        raw = (record["Código"] or "").strip().removesuffix(".0")
        code = raw.zfill(CROP_CODE_LENGTH) if raw.isdigit() and len(raw) == CROP_CODE_LENGTH - 1 else raw
        name = " ".join((record["Nombre"] or "").split())
        row = RegistrationRow(row_number=record["row_number"], code=code, name=name, crop_code=code)
        if not (code.isdigit() and len(code) == CROP_CODE_LENGTH):
            row.errors.append(f"Código '{raw}' inválido: deben ser {CROP_CODE_LENGTH} dígitos")
        elif not is_agricultural(code):
            row.errors.append(f"El cultivo {code} no es de una familia agrícola (01–09)")
        elif code in seen:
            row.errors.append(f"Código repetido (también en la fila {seen[code]})")
        else:
            seen[code] = row.row_number
            if code != raw:
                row.warnings.append(f"Código corregido a {code} (Excel quitó el cero inicial)")
        if not name:
            row.errors.append("Nombre vacío")
        elif len(name) > MAX_CROP_NAME:
            row.errors.append(f"Nombre de más de {MAX_CROP_NAME} caracteres")
        if norm_text(record["Estado"] or "") != norm_text(STATUS_ACTIVE):
            row.errors.append(f"Estado debe ser '{STATUS_ACTIVE}'")
        existing = crops.get(code)
        if existing is not None and row.valid:
            if existing[1]:
                row.warnings.append(f"El cultivo ya existe ({existing[0]})")
            else:
                row.errors.append(
                    f"El cultivo {code} ({existing[0]}) ya existe inactivo: no se reactiva; lo hace el área dueña"
                )
        rows.append(row)
    return rows


def validate_registration(
    sheet: pl.DataFrame, crops: Mapping[str, tuple[str, bool]], existing_codes: Collection[str]
) -> list[RegistrationRow]:
    """Valida cada fila de la hoja `Registro` contra las reglas de D33 (`SPEC-catalog-sync.md`).

    Args:
        sheet: Resultado de `read_registration_sheet`.
        crops: `código de cultivo → (nombre, activo)` de la multi gestión (`BM_TCATCAT`).
        existing_codes: Códigos que ya están en `BM_Catalog` (`type='0001'`, en cualquier estado).

    Returns:
        Una `RegistrationRow` por fila, en orden. Las que ya existen quedan válidas; el llamador las omite.
    """
    rows: list[RegistrationRow] = []
    seen: dict[str, int] = {}
    for record in sheet.iter_rows(named=True):
        code = normalize_code(record["Código"])
        name = " ".join((record["Nombre"] or "").split())
        row = RegistrationRow(row_number=record["row_number"], code=code, name=name, crop_code=code[:4])
        _check_code(row, record["Código"], seen)
        _check_fixed(row, record)
        _check_crop(row, record["Categoria"], crops)
        if not name:
            row.errors.append("Nombre vacío")
        elif len(name) > MAX_NAME:
            row.errors.append(f"Nombre de más de {MAX_NAME} caracteres")
        if record["Cantidad"] or record["Precio"]:
            row.warnings.append("Cantidad y Precio se ignoran")
        if row.valid and code in existing_codes:
            row.warnings.append("El código ya está en el catálogo")
        rows.append(row)
    return rows


def normalize_code(raw: str | None) -> str:
    """Código de 6 dígitos. Si Excel lo guardó como número y perdió el cero inicial (`60902`), lo repone."""
    code = (raw or "").strip()
    if code.endswith(".0"):  # celda numérica leída como texto
        code = code[:-2]
    if code.isdigit() and len(code) == CODE_LENGTH - 1 and not code.startswith("0"):  # "06090" es un error
        return code.zfill(CODE_LENGTH)
    return code


def _check_code(row: RegistrationRow, raw: str | None, seen: dict[str, int]) -> None:
    if not (row.code.isdigit() and len(row.code) == CODE_LENGTH):
        row.errors.append(f"Código '{raw or ''}' inválido: deben ser {CODE_LENGTH} dígitos")
        return
    if row.code != (raw or "").strip():
        row.warnings.append(f"Código corregido a {row.code} (Excel quitó el cero inicial)")
    if row.code in seen:
        row.errors.append(f"Código repetido (también en la fila {seen[row.code]})")
    else:
        seen[row.code] = row.row_number


def _check_fixed(row: RegistrationRow, record: Mapping[str, str | None]) -> None:
    expected = {"Tipo": TYPE_LABEL, "Und. Medida": UNIT_KG, "Estado": STATUS_ACTIVE}
    for column, value in expected.items():
        if norm_text(record[column] or "") != norm_text(value):
            row.errors.append(f"{column} debe ser '{value}'")


def _check_crop(row: RegistrationRow, category: str | None, crops: Mapping[str, tuple[str, bool]]) -> None:
    if not row.code.isdigit() or len(row.code) != CODE_LENGTH:
        return
    crop = crops.get(row.crop_code)
    if crop is None:
        row.errors.append(
            f"El cultivo {row.crop_code} no existe en la multi gestión: agréguelo en la hoja '{CROP_SHEET}'"
        )
        return
    crop_name, active = crop
    if not active:
        row.errors.append(f"El cultivo {row.crop_code} ({crop_name}) está inactivo: primero hay que activarlo")
    if norm_text(category or "") != norm_text(crop_name):
        row.errors.append(
            f"Categoria '{category or ''}' no corresponde al código: el cultivo {row.crop_code} es '{crop_name}'"
        )
