"""Normalización de texto para cruzar nombres del portal SISAP con el catálogo y el ubigeo.

Portado de `_norm` del script legado (`system/utils/merge.py`): sin tildes, en minúsculas y solo
`[a-z0-9]`. Hay dos formas equivalentes: `norm_text` para un valor suelto y `norm_key` como
expresión de Polars para columnas completas.
"""

import re
import unicodedata

import polars as pl

REGION_ALIASES: dict[str, str] = {
    "limametropolitana": "lima",
}
"""Claves normalizadas de región SISAP que se reemplazan antes de buscarlas en `BM_Ubigeo`."""

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def norm_text(value: str | None) -> str:
    """Normaliza un texto: quita tildes, pasa a minúsculas y elimina todo lo que no sea `[a-z0-9]`.

    Args:
        value: Texto a normalizar. `None` se trata como vacío.

    Returns:
        La clave normalizada, p. ej. `"San Martín (Tarapoto)"` → `"sanmartintarapoto"`.
    """
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub("", without_marks.casefold())


def norm_region(value: str | None) -> str:
    """Normaliza un nombre de región y aplica `REGION_ALIASES`."""
    key = norm_text(value)
    return REGION_ALIASES.get(key, key)


def norm_key(column: str) -> pl.Expr:
    """Expresión de Polars equivalente a `norm_text` sobre la columna `column`."""
    return (
        pl.col(column)
        .fill_null("")
        .str.normalize("NFKD")
        .str.replace_all(r"\p{Mn}", "")
        .str.to_lowercase()
        .str.replace_all(r"[^a-z0-9]", "")
    )


def norm_region_key(column: str) -> pl.Expr:
    """Expresión de Polars equivalente a `norm_region` sobre la columna `column`."""
    return norm_key(column).replace(REGION_ALIASES)
