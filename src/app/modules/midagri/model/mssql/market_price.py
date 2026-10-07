"""`dbo.BM_MarketPrice`: precios de todos los mercados SISAP (creada por `sql/0002_create_bm_market_price.sql`)."""

import datetime as dt
import uuid as uuid_lib
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Unicode, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.midagri.model.mssql.base import MssqlBase


class MarketPrice(MssqlBase):
    """Precio mínimo, promedio y máximo de un producto en un mercado y un ubigeo, en un día.

    Misma forma que `CatalogPrice` más `idMarket`. Ningún SP del app la lee: así se cargan todos los mercados
    sin cambiar el reporte (D15'). Sin FK a `BM_Catalog` ni a `BM_Ubigeo` en la BD (el ORM las declara igual).
    """

    __tablename__ = "BM_MarketPrice"
    __table_args__ = (
        UniqueConstraint(
            "idCatalog", "idMarket", "idUbigeo", "date", "unitOfMeasure", "type", name="UQ_BM_MarketPrice_Key"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[uuid_lib.UUID | None] = mapped_column(Uuid, server_default=text("newid()"))
    type: Mapped[str] = mapped_column(Unicode(50))
    id_catalog: Mapped[int] = mapped_column("idCatalog", Integer, ForeignKey("dbo.BM_Catalog.id"))
    id_market: Mapped[int] = mapped_column("idMarket", Integer, ForeignKey("dbo.BM_Market.id"))
    id_ubigeo: Mapped[int] = mapped_column("idUbigeo", Integer, ForeignKey("dbo.BM_Ubigeo.id"))
    date: Mapped[dt.date] = mapped_column(Date)  # `dt.date`: el atributo `date` taparía el tipo
    unit_of_measure: Mapped[str] = mapped_column("unitOfMeasure", Unicode(50))
    equivalence: Mapped[str | None] = mapped_column(Unicode(50))
    min: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    mean: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    max: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    registration_date: Mapped[dt.datetime | None] = mapped_column(
        "registrationDate", DateTime, server_default=text("getdate()")
    )
    registered_by: Mapped[str | None] = mapped_column("registeredBy", String(20), server_default=text("'etl-sisap'"))
