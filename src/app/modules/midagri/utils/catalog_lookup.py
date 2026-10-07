"""Índices en memoria para cruzar precios SISAP con el catálogo y el ubigeo (funciones puras, Polars)."""

import polars as pl

from app.modules.midagri.utils.text import norm_region_key

UBIGEO_LEVEL_PRIORITY: dict[str, int] = {"district": 1, "province": 2, "department": 3}
"""Prioridad del legado al resolver una región SISAP: distrito, luego provincia, luego departamento."""


def first_id_by_code(catalog: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Resuelve `code → id` quedándose con el menor `id` cuando un código está repetido.

    Args:
        catalog: Filas activas de `BM_Catalog` con columnas `code` e `id`.

    Returns:
        Una tupla `(mapping, duplicates)`: `mapping` con `code` e `id` (una fila por código) y
        `duplicates` con `code` e `ids` (lista ordenada) para los códigos que aparecen más de una vez.
    """
    grouped = (
        catalog.lazy()
        .filter(pl.col("code").is_not_null())
        .group_by("code")
        .agg(pl.col("id").min().alias("id"), pl.col("id").sort().alias("ids"))
        .sort("code")
        .collect()
    )
    mapping = grouped.select("code", "id")
    duplicates = grouped.filter(pl.col("ids").list.len() > 1).select("code", "ids")
    return mapping, duplicates


def build_region_lookup(ubigeo: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Construye el índice `key → id` para resolver una región SISAP contra `BM_Ubigeo`.

    Cada fila aporta su nombre de distrito, provincia y departamento como candidatos. Para una misma
    clave gana el nivel de mayor prioridad (distrito > provincia > departamento, como el legado) y,
    dentro del mismo nivel, el menor `id` (el legado tomaba uno arbitrario).

    Args:
        ubigeo: Filas de `BM_Ubigeo` con `id`, `department`, `province` y `district`.

    Returns:
        Una tupla `(lookup, ambiguous)`: `lookup` con `key` e `id`, y `ambiguous` con las claves que
        el nivel ganador comparte entre varios ids (`key`, `level`, `ids`).
    """
    candidates = (
        ubigeo.lazy()
        .select("id", *UBIGEO_LEVEL_PRIORITY)
        .unpivot(index="id", on=list(UBIGEO_LEVEL_PRIORITY), variable_name="level", value_name="name")
        .filter(pl.col("name").is_not_null())
        .with_columns(
            key=norm_region_key("name"),
            priority=pl.col("level").replace_strict(UBIGEO_LEVEL_PRIORITY, return_dtype=pl.Int8),
        )
        .filter(pl.col("key") != "")
        .unique(subset=["key", "priority", "id"])
    )
    winners = (
        candidates.filter(pl.col("priority") == pl.col("priority").min().over("key"))
        .group_by("key")
        .agg(
            pl.col("id").min().alias("id"),
            pl.col("id").sort().alias("ids"),
            pl.col("level").first().alias("level"),
        )
        .sort("key")
        .collect()
    )
    lookup = winners.select("key", "id")
    ambiguous = winners.filter(pl.col("ids").list.len() > 1).select("key", "level", "ids")
    return lookup, ambiguous
