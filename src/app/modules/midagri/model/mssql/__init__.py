"""Modelos de SQL Server (`BDFARMEX`): tablas de negocio."""

from app.modules.midagri.model.mssql.base import MssqlBase
from app.modules.midagri.model.mssql.catalog import Catalog
from app.modules.midagri.model.mssql.catalog_price import CatalogPrice
from app.modules.midagri.model.mssql.market import Market
from app.modules.midagri.model.mssql.market_price import MarketPrice
from app.modules.midagri.model.mssql.multitabla import Multitabla
from app.modules.midagri.model.mssql.multivalor import Multivalor
from app.modules.midagri.model.mssql.ubigeo import Ubigeo

__all__: list[str] = [
    "Catalog",
    "CatalogPrice",
    "Market",
    "MarketPrice",
    "MssqlBase",
    "Multitabla",
    "Multivalor",
    "Ubigeo",
]
