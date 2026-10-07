"""`dbo.BM_CatalogPrice`: precios que lee el SP de reportes del app. Tabla existente, sin cambios de esquema."""

import datetime as dt
import uuid as uuid_lib
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Unicode, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.midagri.model.mssql.base import MssqlBase


class CatalogPrice(MssqlBase):
    """Precio mínimo, promedio y máximo de un producto en un ubigeo, en un día. Solo mercado 15011501 (D15').

    Lo lee `uspBM_GetDynamicCatalogPriceReport`, que no distingue mercado: por eso aquí solo entra el mercado
    que cargaba el legado. Todos los mercados van a `MarketPrice`. Las filas tienen `unitOfMeasure='Kg'`,
    `equivalence=''`, `type='Mayorista'` y `registeredBy='etl-sisap'`. La llave lógica es
    `(idCatalog, idUbigeo, date, unitOfMeasure, type)`, sin restricción única en la BD.
    """

    __tablename__ = "BM_CatalogPrice"

    uuid: Mapped[uuid_lib.UUID | None] = mapped_column(Uuid, server_default=text("newid()"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str | None] = mapped_column(Unicode(50))
    id_catalog: Mapped[int] = mapped_column("idCatalog", Integer, ForeignKey("dbo.BM_Catalog.id"))
    id_ubigeo: Mapped[int | None] = mapped_column("idUbigeo", Integer, ForeignKey("dbo.BM_Ubigeo.id"))
    date: Mapped[dt.date] = mapped_column(Date)  # `dt.date`: el atributo `date` taparía el tipo
    unit_of_measure: Mapped[str | None] = mapped_column("unitOfMeasure", Unicode(50))
    equivalence: Mapped[str | None] = mapped_column(Unicode(50))
    min: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    mean: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    max: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    registration_date: Mapped[dt.datetime | None] = mapped_column(
        "registrationDate", DateTime, server_default=text("getdate()")
    )
    registered_by: Mapped[str | None] = mapped_column("registeredBy", String(20))
