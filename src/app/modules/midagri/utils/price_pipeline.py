"""De precios descargados a filas de `BM_MarketPrice` (funciones puras, Polars).

Cada paso separa lo que **no** se carga, con su motivo, para que quede en el log de la ejecución. Nada se
"adivina": una fila dudosa se rechaza (D28).

Orden: `validate_prices` → (`to_kg`, solo Ciudades) → `to_upsert_rows`.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import polars as pl

from app.modules.midagri.repository.interface.price_repository import UPSERT_SCHEMA
from app.modules.midagri.utils.text import norm_key, norm_region_key

PRICES = ("min", "mean", "max")
PRICE_TYPE = "Mayorista"
"""`type` de todas las filas (el SP de reportes no lo filtra; en `BM_MarketPrice` el mercado distingue el origen)."""
UNIT_KG = "Kg"
REGISTERED_BY = "etl-sisap"
PLAUSIBLE_RATIO = 5
"""Un precio por kg convertido se rechaza si está a más de ×5 (o ÷5) de la mediana de las regiones en kg."""

REJECTED_SCHEMA: dict[str, pl.DataType] = {
    "variety_code": pl.String(),
    "variety_name": pl.String(),
    "region": pl.String(),
    "date": pl.Date(),
    "unit": pl.String(),
    "equivalence": pl.Decimal(18, 4),
    "mean": pl.Decimal(18, 4),
    "reason": pl.String(),
}
"""Filas descartadas, con el motivo."""


@dataclass(frozen=True, slots=True)
class UpsertRows:
    """Resultado de `to_upsert_rows`: filas para cargar, códigos sin catálogo y filas descartadas."""

    rows: pl.DataFrame
    unmatched_codes: list[str]
    unmatched: int
    rejected: pl.DataFrame


def empty_rejected() -> pl.DataFrame:
    """DataFrame de rechazos vacío."""
    return pl.DataFrame(schema=REJECTED_SCHEMA)


def _rejected(frame: pl.LazyFrame) -> pl.DataFrame:
    return frame.select(list(REJECTED_SCHEMA)).collect().cast(pl.Schema(REJECTED_SCHEMA))


def validate_prices(rows: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Descarta filas con precios incoherentes: todos nulos, alguno ≤ 0 o `min ≤ prom ≤ máx` roto.

    Returns:
        `(válidas, rechazadas)`.
    """
    present = pl.col(*PRICES)
    lf = rows.lazy().with_columns(
        reason=pl.when(pl.all_horizontal(present.is_null()))
        .then(pl.lit("sin precios"))
        .when(pl.any_horizontal(present <= 0))
        .then(pl.lit("precio ≤ 0"))
        .when((pl.col("min") > pl.col("mean")) | (pl.col("mean") > pl.col("max")) | (pl.col("min") > pl.col("max")))
        .then(pl.lit("no cumple mín ≤ prom ≤ máx"))
    )
    valid = lf.filter(pl.col("reason").is_null()).drop("reason").collect()
    return valid, _rejected(lf.filter(pl.col("reason").is_not_null()))


def to_kg(rows: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Convierte precios de Ciudades a S/ por kg: precio ÷ equivalencia (kg por unidad de venta).

    Rechaza: equivalencia vacía o ≤ 0; unidad "Kilogramo" con equivalencia ≠ 1; precio **convertido** a más de
    ×5 o ÷5 de la mediana del mismo producto y día entre las regiones que publican en kg (un precio publicado en kg
    no se rechaza por atípico). Si una región publica el mismo
    producto y día en varias unidades, gana "Kilogramo" y, si no, la de menor equivalencia.
    Probado con la semana real al 2026-09-24: 2 943 filas → 2 940 convertidas.

    Returns:
        `(convertidas, rechazadas)`. Las convertidas quedan con `unit="Kg"` y `equivalence=1`.
    """
    is_kg_unit = norm_key("unit") == "kilogramo"
    lf = rows.lazy().with_columns(
        is_kg_unit=is_kg_unit,
        reason=pl.when(pl.col("equivalence").is_null() | (pl.col("equivalence") <= 0))
        .then(pl.lit("equivalencia vacía o ≤ 0"))
        .when(is_kg_unit & (pl.col("equivalence") != 1))
        .then(pl.lit("unidad Kilogramo con equivalencia distinta de 1")),
    )
    rejected = [_rejected(lf.filter(pl.col("reason").is_not_null()))]
    converted = (
        lf.filter(pl.col("reason").is_null())
        .with_columns([(pl.col(c) / pl.col("equivalence")).round(4).cast(pl.Decimal(18, 4)).alias(c) for c in PRICES])
        .with_columns(
            kg_median=pl.col("mean").filter(pl.col("is_kg_unit")).median().over("variety_code", "date"),
        )
        .with_columns(
            # Solo filas convertidas desde otra unidad: la regla atrapa errores de conversión (una "Bolsa" que en
            # realidad era un precio por kg). Un precio publicado en kg se respeta aunque sea atípico.
            reason=pl.when(
                ~pl.col("is_kg_unit")
                & pl.col("kg_median").is_not_null()
                & (
                    (pl.col("mean").cast(pl.Float64) > pl.col("kg_median").cast(pl.Float64) * PLAUSIBLE_RATIO)
                    | (pl.col("mean").cast(pl.Float64) * PLAUSIBLE_RATIO < pl.col("kg_median").cast(pl.Float64))
                )
            ).then(pl.lit(f"precio por kg a más de ×{PLAUSIBLE_RATIO} de la mediana de las regiones en kg"))
        )
    )
    rejected.append(_rejected(converted.filter(pl.col("reason").is_not_null())))
    kept = (
        converted.filter(pl.col("reason").is_null())
        .sort(
            ["variety_code", "region", "date", "is_kg_unit", "equivalence"],
            descending=[False, False, False, True, False],
        )
        .unique(subset=["variety_code", "region", "date"], keep="first", maintain_order=True)
        .with_columns(unit=pl.lit(UNIT_KG), equivalence=pl.lit(1, dtype=pl.Decimal(18, 4)))
        .drop("is_kg_unit", "kg_median", "reason")
        .collect()
    )
    return kept, pl.concat(rejected)


def to_upsert_rows(
    rows: pl.DataFrame,
    *,
    market_id: int,
    catalog_ids: Mapping[str, int],
    region_lookup: pl.DataFrame,
) -> UpsertRows:
    """Resuelve código → `idCatalog` y región → `idUbigeo` y consolida una fila por llave.

    Args:
        rows: Precios válidos (y, en Ciudades, ya en kg) con `variety_code`, `region`, `date`, `unit` y precios.
        market_id: `BM_Market.id`.
        catalog_ids: `code → idCatalog` de productos activos (`CatalogRepository.map_active_by_code`).
        region_lookup: `key → id` de `UbigeoRepository.region_lookup`.

    Returns:
        Filas con `UPSERT_SCHEMA`; los códigos sin producto activo (`unmatched`) y las filas sin ubigeo (rechazadas).
    """
    mapping = pl.DataFrame(
        {"variety_code": list(catalog_ids), "id_catalog": list(catalog_ids.values())},
        schema={"variety_code": pl.String, "id_catalog": pl.Int64},
    )
    resolved = (
        rows.lazy()
        .join(mapping.lazy(), on="variety_code", how="left")
        .with_columns(key=norm_region_key("region"))
        .join(region_lookup.lazy().rename({"id": "id_ubigeo"}), on="key", how="left")
    )
    unmatched_frame = resolved.filter(pl.col("id_catalog").is_null()).collect()
    rejected = _rejected(
        resolved.filter(pl.col("id_catalog").is_not_null(), pl.col("id_ubigeo").is_null()).with_columns(
            reason=pl.lit("región sin ubigeo")
        )
    )
    upsert = (
        resolved.filter(pl.col("id_catalog").is_not_null(), pl.col("id_ubigeo").is_not_null())
        .group_by("id_catalog", "id_ubigeo", "date")
        .agg(pl.col(*PRICES).max())  # mismo producto repetido en la tabla: se consolida como el legado (máximo)
        .with_columns(
            id_market=pl.lit(market_id, dtype=pl.Int64),
            unit_of_measure=pl.lit(UNIT_KG),
            type=pl.lit(PRICE_TYPE),
            equivalence=pl.lit(""),
            registered_by=pl.lit(REGISTERED_BY),
        )
        .select(list(UPSERT_SCHEMA))
        .sort("id_catalog", "id_ubigeo", "date")
        .collect()
        .cast(pl.Schema(UPSERT_SCHEMA))
    )
    return UpsertRows(
        rows=upsert,
        unmatched_codes=sorted(unmatched_frame["variety_code"].drop_nulls().unique().to_list()),
        unmatched=unmatched_frame.height,
        rejected=rejected,
    )
