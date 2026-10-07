"""Clasificación de faltantes del catálogo (función pura, Polars). Reglas de D2, D5, D6 y D14.

| Estado | Condición |
|---|---|
| `ESC1` | El cultivo (4 dígitos) **no existe** en `BM_TCATCAT`, ni activo ni inactivo. Solo se reporta (D14). |
| `ESC2` | El cultivo existe **activo** y la variedad no existe en `BM_Catalog`. |
| excluido | El cultivo existe **inactivo** (D6), o la familia no es agrícola 01–09 (D5). |

Una variedad es faltante si tuvo precio en el periodo y su código no está en `BM_Catalog` (`type='0001'`),
en ningún estado: si existe inactiva no se crea otra (sería un duplicado).
"""

from collections.abc import Collection, Iterable, Mapping, Sequence

import polars as pl

from app.modules.midagri.model.sisap import SisapGenre, SisapVariety

AGRICULTURAL_FAMILIES: tuple[str, ...] = tuple(f"{n:02d}" for n in range(1, 10))
"""Familias agrícolas (2 primeros dígitos del código). Fuera: abarrotes y pecuarios 10–13 (D5)."""

PRICED_SCHEMA: dict[str, pl.DataType] = {
    "variety_code": pl.String(),
    "variety_name": pl.String(),
    "genre_code": pl.String(),
    "genre_name": pl.String(),
    "market": pl.String(),
    "last_price_date": pl.Date(),
    "price_date": pl.Date(),
    "price_min": pl.Decimal(18, 4),
    "price_mean": pl.Decimal(18, 4),
    "price_max": pl.Decimal(18, 4),
}
"""Variedades con precio en el periodo, una fila por variedad y mercado.

`price_*`: precio del último día con precio **válido** en S/ por kg (`attach_last_prices`); nulo si todas sus
filas se rechazaron por calidad o si no se calculó.
"""

PRICE_COLUMNS: tuple[str, ...] = ("price_date", "price_min", "price_mean", "price_max")

MARKET_PRICE_TYPE = pl.Struct(
    {
        "market": pl.String(),
        "price_date": pl.Date(),
        "min": pl.Decimal(18, 4),
        "mean": pl.Decimal(18, 4),
        "max": pl.Decimal(18, 4),
    }
)

GAP_SCHEMA: dict[str, pl.DataType] = {
    "status": pl.String(),
    "variety_code": pl.String(),
    "variety_name": pl.String(),
    "crop_code": pl.String(),
    "crop_name": pl.String(),
    "markets": pl.List(pl.String()),
    "last_price_date": pl.Date(),
    "prices": pl.List(MARKET_PRICE_TYPE),
}


def is_agricultural(code: str) -> bool:
    """Indica si un código de género o variedad es de una familia agrícola 01–09."""
    return code[:2] in AGRICULTURAL_FAMILIES


def relevant_genres(genres: Iterable[SisapGenre], inactive_crops: Collection[str]) -> list[SisapGenre]:
    """Géneros a consultar: familias agrícolas 01–09 (D5) y cultivos que no están inactivos (D6).

    Se incluyen los cultivos que no existen en la multi gestión: sus variedades son los ESC1 del reporte.
    """
    return [genre for genre in genres if is_agricultural(genre.code) and genre.code not in inactive_crops]


def priced_varieties(
    rows: pl.DataFrame, varieties: Sequence[SisapVariety], genre_names: Mapping[str, str], market: str
) -> pl.DataFrame:
    """Variedades con al menos un precio en `rows` (la descarga de un mercado), con su última fecha.

    Args:
        rows: Precios descargados (`PRICE_SCHEMA` de `model/sisap.py`).
        varieties: Variedades consultadas (dan el nombre de catálogo y el género).
        genre_names: Nombre de cada género.
        market: Nombre del mercado para el reporte (`MarketRef.label`).

    Returns:
        Un DataFrame con `PRICED_SCHEMA`.
    """
    info = pl.DataFrame(
        {
            "variety_code": [v.code for v in varieties],
            "variety_name": [v.name for v in varieties],
            "genre_code": [v.genre_code for v in varieties],
            "genre_name": [genre_names.get(v.genre_code, v.genre_code) for v in varieties],
        },
        schema={k: PRICED_SCHEMA[k] for k in ("variety_code", "variety_name", "genre_code", "genre_name")},
    ).unique("variety_code", keep="first")
    return (
        rows.lazy()
        .filter(pl.col("variety_code").is_not_null())
        .group_by("variety_code")
        .agg(pl.col("date").max().alias("last_price_date"))
        .join(info.lazy(), on="variety_code", how="inner")
        .with_columns(market=pl.lit(market), **{column: pl.lit(None) for column in PRICE_COLUMNS})
        .select(list(PRICED_SCHEMA))
        .collect()
        .cast(pl.Schema(PRICED_SCHEMA))
    )


def attach_last_prices(priced: pl.DataFrame, prices: pl.DataFrame) -> pl.DataFrame:
    """Agrega a cada variedad el precio de su último día en `prices`.

    Args:
        priced: Resultado de `priced_varieties` (un mercado).
        prices: Precios **válidos** del mismo mercado en S/ por kg (tras `validate_prices` y, en Ciudades, `to_kg`),
            con `variety_code`, `date`, `min`, `mean` y `max`.

    Returns:
        `priced` con `price_date`, `price_min` (el menor), `price_mean` (promedio de los promedios: en Ciudades,
        de las regiones) y `price_max` (el mayor) de ese día, redondeados a 4 decimales.
    """
    valid = prices.lazy().filter(pl.col("variety_code").is_not_null(), pl.col("mean").is_not_null())
    last_day = valid.group_by("variety_code").agg(pl.col("date").max().alias("price_date"))
    last = (
        valid.join(last_day, on="variety_code")
        .filter(pl.col("date") == pl.col("price_date"))
        .group_by("variety_code")
        .agg(
            pl.col("price_date").first(),
            pl.col("min").cast(pl.Float64).min().alias("price_min"),
            pl.col("mean").cast(pl.Float64).mean().alias("price_mean"),
            pl.col("max").cast(pl.Float64).max().alias("price_max"),
        )
        .with_columns(pl.col("price_min", "price_mean", "price_max").round(4))
    )
    return (
        priced.lazy()
        .drop(PRICE_COLUMNS)
        .join(last, on="variety_code", how="left")
        .select(list(PRICED_SCHEMA))
        .collect()
        .cast(pl.Schema(PRICED_SCHEMA))
    )


def classify_gaps(priced: pl.DataFrame, crops: pl.DataFrame, existing_codes: Iterable[str]) -> pl.DataFrame:
    """Faltantes ESC1/ESC2 ordenados por escenario y código.

    Args:
        priced: Variedades con precio (`PRICED_SCHEMA`), una fila por variedad y mercado.
        crops: Cultivos de la multi gestión, activos e inactivos: `code`, `name`, `active`.
        existing_codes: Códigos de variedad que ya están en `BM_Catalog` (cualquier estado).

    Returns:
        Un DataFrame con `GAP_SCHEMA`.
    """
    existing = pl.Series("code", list(existing_codes), dtype=pl.String)
    by_variety = (
        priced.lazy()
        .sort("last_price_date", nulls_last=False)
        .unique(["variety_code", "market"], keep="last", maintain_order=True)  # una fila por variedad y mercado
        .filter(pl.col("variety_code").str.slice(0, 2).is_in(AGRICULTURAL_FAMILIES))
        .filter(~pl.col("variety_code").is_in(existing.implode()))
        .group_by("variety_code")
        .agg(
            pl.col("variety_name").first(),
            pl.col("genre_code").first().alias("crop_code"),
            pl.col("genre_name").first(),
            pl.col("market").unique().sort().alias("markets"),
            pl.col("last_price_date").max(),
            pl.struct(
                pl.col("market"),
                pl.col("price_date"),
                pl.col("price_min").alias("min"),
                pl.col("price_mean").alias("mean"),
                pl.col("price_max").alias("max"),
            )
            .sort_by("market")
            .alias("prices"),
        )
    )
    crop_status = crops.lazy().select(
        pl.col("code").alias("crop_code"), pl.col("name").alias("crop_db_name"), pl.col("active")
    )
    return (
        by_variety.join(crop_status, on="crop_code", how="left")
        .with_columns(
            status=pl.when(pl.col("active").is_null())
            .then(pl.lit("ESC1"))
            .when(pl.col("active"))
            .then(pl.lit("ESC2"))
            .otherwise(pl.lit(None, dtype=pl.String)),
            crop_name=pl.coalesce("crop_db_name", "genre_name"),
        )
        .filter(pl.col("status").is_not_null())  # cultivo inactivo: no se muestra ni se toca (D6)
        .select(list(GAP_SCHEMA))
        .sort("status", "variety_code")
        .collect()
        .cast(pl.Schema(GAP_SCHEMA))
    )
