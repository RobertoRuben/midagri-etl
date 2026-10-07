"""`dbo.BM_Market`: mercados SISAP que carga la API (creada por `sql/0001_create_bm_market.sql`)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.midagri.model.mssql.base import MssqlBase


class Market(MssqlBase):
    """Mercado. Se activa o desactiva con `active` (sin redesplegar): así se habilita un mercado por fase."""

    __tablename__ = "BM_Market"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(20))
    """`MAYORISTA` o `CIUDADES`."""
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("1"))
    registration_date: Mapped[datetime | None] = mapped_column(
        "registrationDate", DateTime, server_default=text("getdate()")
    )
    registered_by: Mapped[str | None] = mapped_column("registeredBy", String(20), server_default=text("'etl-sisap'"))
    edit_date: Mapped[datetime | None] = mapped_column("editDate", DateTime)
    edited_by: Mapped[str | None] = mapped_column("editedBy", String(20))
