"""Mercados y precios en SQL Server. Upsert masivo con `#TmpPrices` + `UPDATE`/`INSERT` (reemplaza `merge_prices`)."""

from dataclasses import dataclass

import polars as pl
from sqlalchemy import Column, Date, Integer, MetaData, Numeric, String, Table, Unicode, insert, select, text, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.repository.impl.generic_repository_impl import GenericRepositoryImpl
from app.modules.midagri.model.mssql import Market, MarketPrice
from app.modules.midagri.repository.interface.price_repository import (
    REPORT_KEY,
    UPSERT_KEY,
    UPSERT_SCHEMA,
    MarketRepository,
    PriceRepository,
    UpsertResult,
)

_TMP = "#TmpPrices"
_tmp_prices = Table(
    _TMP,
    MetaData(),
    Column("id_catalog", Integer, nullable=False),
    Column("id_market", Integer, nullable=False),
    Column("id_ubigeo", Integer, nullable=False),
    Column("date", Date, nullable=False),
    Column("unit_of_measure", Unicode(50), nullable=False),
    Column("type", Unicode(50), nullable=False),
    Column("equivalence", Unicode(50)),
    Column("min", Numeric(18, 4)),
    Column("mean", Numeric(18, 4)),
    Column("max", Numeric(18, 4)),
    Column("registered_by", String(20)),
)
"""Tabla temporal local de la conexión: desaparece al cerrarla y no choca entre ejecuciones."""

_COLUMN = {
    "id_catalog": "idCatalog",
    "id_market": "idMarket",
    "id_ubigeo": "idUbigeo",
    "date": "[date]",
    "unit_of_measure": "unitOfMeasure",
    "type": "[type]",
}
_CHANGED = """
    EXISTS (SELECT T.[min], T.mean, T.[max], T.equivalence EXCEPT SELECT S.[min], S.mean, S.[max], S.equivalence)
"""
# EXCEPT compara con NULL = NULL: detecta cambios también cuando un precio pasa de nulo a valor o al revés.


@dataclass(frozen=True, slots=True)
class _Target:
    """Tabla destino del upsert: su nombre y su llave (columnas de `UPSERT_SCHEMA`)."""

    table: str
    key: tuple[str, ...]

    @property
    def match(self) -> str:
        return " AND ".join(f"T.{_COLUMN[column]} = S.{column}" for column in self.key)

    @property
    def update_sql(self) -> str:
        return f"""
UPDATE T SET T.[min] = S.[min], T.mean = S.mean, T.[max] = S.[max], T.equivalence = S.equivalence,
             T.registeredBy = S.registered_by
FROM {self.table} AS T WITH (ROWLOCK)
JOIN {_TMP} AS S ON {self.match}
WHERE {_CHANGED};
"""

    @property
    def insert_sql(self) -> str:
        with_market = "id_market" in self.key
        market_column = ", idMarket" if with_market else ""
        market_value = ", S.id_market" if with_market else ""
        return f"""
INSERT INTO {self.table}
    ([type], idCatalog, idUbigeo{market_column}, [date], unitOfMeasure, equivalence, [min], mean, [max], registeredBy)
SELECT S.[type], S.id_catalog, S.id_ubigeo{market_value}, S.[date], S.unit_of_measure, S.equivalence,
       S.[min], S.mean, S.[max], S.registered_by
FROM {_TMP} AS S
WHERE NOT EXISTS (SELECT 1 FROM {self.table} AS T WHERE {self.match});
"""


_MARKET_PRICE = _Target("dbo.BM_MarketPrice", UPSERT_KEY)
_CATALOG_PRICE = _Target("dbo.BM_CatalogPrice", REPORT_KEY)


class MarketRepositoryImpl(GenericRepositoryImpl[Market], MarketRepository):
    """Mercados en SQL Server."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Market, session)

    async def list_active(self) -> list[Market]:
        return list(await self.session.scalars(select(Market).where(Market.active == true()).order_by(Market.code)))

    async def get_by_code(self, code: str) -> Market | None:
        return await self.get_by(Market.code, code)


class PriceRepositoryImpl(GenericRepositoryImpl[MarketPrice], PriceRepository):
    """Precios en SQL Server. La transacción la maneja el service (una por mercado)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(MarketPrice, session)

    async def upsert(self, prices: pl.DataFrame) -> UpsertResult:
        return await self._upsert(prices, _MARKET_PRICE)

    async def upsert_report(self, prices: pl.DataFrame) -> UpsertResult:
        return await self._upsert(prices, _CATALOG_PRICE)

    async def _upsert(self, prices: pl.DataFrame, target: _Target) -> UpsertResult:
        _validate(prices, target)
        if prices.is_empty():
            return UpsertResult(inserted=0, updated=0, unchanged=0)
        # pyodbc con fast_executemany rechaza Decimal en tablas #temporales ("Converting decimal loses
        # precision"): los precios viajan como texto con 4 decimales y SQL Server los convierte sin pérdida (D23).
        rows = prices.select(list(UPSERT_SCHEMA)).with_columns(pl.col("min", "mean", "max").cast(pl.String)).to_dicts()

        await self.session.execute(text(f"IF OBJECT_ID('tempdb..{_TMP}') IS NOT NULL DROP TABLE {_TMP};"))
        await self.session.run_sync(lambda sync_session: _tmp_prices.create(sync_session.connection()))
        try:
            await self.session.execute(insert(_tmp_prices), rows)
            updated = (await self.session.execute(text(target.update_sql))).rowcount  # ty: ignore[unresolved-attribute]
            inserted = (await self.session.execute(text(target.insert_sql))).rowcount  # ty: ignore[unresolved-attribute]
        finally:
            await self.session.execute(text(f"DROP TABLE {_TMP};"))
        return UpsertResult(inserted=inserted, updated=updated, unchanged=len(rows) - inserted - updated)


def _validate(prices: pl.DataFrame, target: _Target) -> None:
    missing = [column for column in UPSERT_SCHEMA if column not in prices.columns]
    if missing:
        raise ValueError(f"Faltan columnas para el upsert de precios: {missing}")
    null_keys = [column for column in UPSERT_KEY if prices[column].null_count()]
    if null_keys:
        raise ValueError(f"La llave del precio no puede ser nula: {null_keys}")
    repeated = prices.height - prices.select(target.key).n_unique()
    if repeated:
        raise ValueError(f"{repeated} filas repiten la llave de {target.table}; deben consolidarse antes del upsert")
