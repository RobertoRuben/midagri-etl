"""`dbo.BM_Catalog`: catálogo de productos (ajena, solo lectura en la fase 1)."""

import uuid as uuid_lib
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.midagri.model.mssql.base import MssqlBase


class Catalog(MssqlBase):
    """Producto del catálogo. Los de mercado tienen `type='0001'` y `code` SISAP de 6 dígitos.

    `category` es el código del cultivo (4 dígitos) y se cruza con `Multivalor.valor`.
    """

    __tablename__ = "BM_Catalog"

    uuid: Mapped[uuid_lib.UUID | None] = mapped_column(Uuid, server_default=text("newid()"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    process: Mapped[str | None] = mapped_column(String(200))
    type: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(50))
    sub_category: Mapped[str | None] = mapped_column("subCategory", String(50))
    code: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str | None] = mapped_column(String(2500))
    nickname: Mapped[str | None] = mapped_column(String(2500))
    description: Mapped[str | None] = mapped_column(String(3500))
    unit_of_measure: Mapped[str | None] = mapped_column("unitOfMeasure", String(20))
    net_weight: Mapped[Decimal | None] = mapped_column("netWeight", Numeric(18, 2))
    max_packaging: Mapped[int | None] = mapped_column("maxPackaging", Integer)
    format: Mapped[str | None] = mapped_column(String(100))
    gauge: Mapped[str | None] = mapped_column(String(100))
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    piece_count: Mapped[str | None] = mapped_column("pieceCount", String(20))
    dimension: Mapped[str | None] = mapped_column(String(20))
    gross_weight: Mapped[Decimal | None] = mapped_column("grossWeight", Numeric(18, 2))
    unit_measure_weight: Mapped[str | None] = mapped_column("unitMeasureWeight", String(50))
    id_branch_organization: Mapped[int | None] = mapped_column("idBranchOrganization", Integer)
    creation_date: Mapped[date | None] = mapped_column("creationDate", Date)
    id_parent: Mapped[int | None] = mapped_column("idParent", Integer)
    id_organization: Mapped[int | None] = mapped_column("idOrganization", Integer)
    active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("1"))
    deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("0"))
    registration_date: Mapped[datetime | None] = mapped_column(
        "registrationDate", DateTime, server_default=text("getdate()")
    )
    registered_by: Mapped[str | None] = mapped_column("registeredBy", String(20), server_default=text("'System'"))
    edit_date: Mapped[datetime | None] = mapped_column("editDate", DateTime)
    edited_by: Mapped[str | None] = mapped_column("editedBy", String(20))
    deletion_date: Mapped[datetime | None] = mapped_column("deletionDate", DateTime)
    deleted_by: Mapped[str | None] = mapped_column("deletedBy", String(20))
    center: Mapped[str | None] = mapped_column("Center", String(100))
    image: Mapped[str | None] = mapped_column(String)
