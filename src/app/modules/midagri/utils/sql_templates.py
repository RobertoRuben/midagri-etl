"""Plantillas del alta de cultivos y variedades con los SP oficiales (D17).

**Una sola definición** genera las dos salidas, para que nunca diverjan:

- `render_*_sql(values)`: el SQL de una fila (fase 2, carga automática).
- `*_sql_formula(row, columns)`: la fórmula de la columna `sql` del Excel, que arma ese mismo SQL a partir de
  las celdas de la fila (el revisor puede corregir un código o un nombre y la fórmula se recalcula).

Cada sentencia es idempotente (`IF NOT EXISTS`) y usa el SP de la aplicación. Verificadas en QAS el
2026-09-24 (`sql/verificacion_carga_catalogo_qas.sql`).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

Escape = Literal["raw", "sql", "xml"]


@dataclass(frozen=True, slots=True)
class Field:
    """Hueco de la plantilla: el valor de una columna, escapado según dónde va dentro del SQL."""

    column: str
    escape: Escape = "raw"


Template = tuple[str | Field, ...]

MULTIVALOR_TEMPLATE: Template = (
    "IF NOT EXISTS (SELECT 1 FROM dbo.IT_Multivalor WHERE Tabla='",
    Field("Tabla"),
    "' AND Valor='",
    Field("Valor"),
    "' AND idOrganization=",
    Field("idOrganization"),
    ') EXEC dbo.uspIT_GuardarActualizarMultivalores @xmlMultivalores=N\'<root><item MultivalorId="0" Valor="',
    Field("Valor"),
    '" Nombre="',
    Field("Nombre", "xml"),
    '" Valor1="',
    Field("Valor1"),
    '" SystemCodeCluster="',
    Field("SystemCodeCluster"),
    "\"/></root>', @idMultitabla=",
    Field("MultitablaId"),
    ", @tablaMultitabla='",
    Field("Tabla"),
    "', @usuario='",
    Field("usuario"),
    "', @idOrganization=",
    Field("idOrganization"),
    ";",
)
"""Alta de un cultivo en `IT_Multivalor` (`BM_TCATCAT`). El `IF NOT EXISTS` mira activos e inactivos, porque
el SP solo valida contra los activos y crearía un duplicado."""

CATALOG_TEMPLATE: Template = (
    "IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='",
    Field("type"),
    "' AND code='",
    Field("code"),
    "' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='",
    Field("process"),
    "', @type='",
    Field("type"),
    "', @category='",
    Field("category"),
    "', @subCategory=NULL, @code='",
    Field("code"),
    "', @name='",
    Field("name", "sql"),
    "', @nickname=NULL, @description=NULL, @unitOfMeasure='",
    Field("unitOfMeasure"),
    "', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, "
    "@dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=",
    Field("idOrganization"),
    ", @active=",
    Field("active"),
    ", @User='",
    Field("usuario"),
    "', @imagenUrl=NULL;",
)
"""Alta de una variedad en `BM_Catalog` con `uspBM_SaveUpdateCatalogo @id=0`."""


# --- SQL (fase 2) ---------------------------------------------------------------------------


def render_sql(template: Template, values: Mapping[str, object]) -> str:
    """Arma el SQL de una fila.

    Raises:
        KeyError: Si falta una columna de la plantilla en `values`.
    """
    return "".join(
        part if isinstance(part, str) else _escape(str(values[part.column]), part.escape) for part in template
    )


def render_multivalor_sql(values: Mapping[str, object]) -> str:
    """SQL del alta de un cultivo."""
    return render_sql(MULTIVALOR_TEMPLATE, values)


def render_catalog_sql(values: Mapping[str, object]) -> str:
    """SQL del alta de una variedad."""
    return render_sql(CATALOG_TEMPLATE, values)


def _escape(value: str, escape: Escape) -> str:
    if escape == "sql":
        return value.replace("'", "''")
    if escape == "xml":  # dentro de un atributo XML que a su vez va en un literal SQL
        return value.replace("&", "&amp;").replace('"', "&quot;").replace("'", "''")
    return value


# --- Fórmula de Excel -----------------------------------------------------------------------


def sql_formula(template: Template, row: int, columns: Mapping[str, str], *, approved_column: str) -> str:
    """Fórmula que arma el SQL de la fila `row` solo si la columna de aprobación dice `SI`.

    Args:
        template: Plantilla (`MULTIVALOR_TEMPLATE` o `CATALOG_TEMPLATE`).
        row: Fila de Excel (1 = encabezado).
        columns: Letra de columna de cada campo de la plantilla (`{"code": "E", ...}`).
        approved_column: Letra de la columna `aprobado`.
    """
    pieces: list[str] = []
    for part in template:
        if isinstance(part, str):
            pieces.append('"' + part.replace('"', '""') + '"')
        else:
            pieces.append(_escape_formula(f"{columns[part.column]}{row}", part.escape))
    body = "&".join(pieces)
    return f'=IF(${approved_column}{row}="SI",{body},"")'


def multivalor_sql_formula(row: int, columns: Mapping[str, str], *, approved_column: str = "A") -> str:
    """Fórmula de la columna `sql` de la hoja `1_IT_Multivalor`."""
    return sql_formula(MULTIVALOR_TEMPLATE, row, columns, approved_column=approved_column)


def catalog_sql_formula(row: int, columns: Mapping[str, str], *, approved_column: str = "A") -> str:
    """Fórmula de la columna `sql` de la hoja `2_BM_Catalog`."""
    return sql_formula(CATALOG_TEMPLATE, row, columns, approved_column=approved_column)


def _escape_formula(cell: str, escape: Escape) -> str:
    if escape == "sql":
        return f'SUBSTITUTE({cell},"\'","\'\'")'
    if escape == "xml":
        return f'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE({cell},"&","&amp;"),"""","&quot;"),"\'","\'\'")'
    return cell
