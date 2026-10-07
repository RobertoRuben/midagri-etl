"""`price_load`: resultado de la carga de precios de un mercado dentro de una ejecución (PostgreSQL)."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.common.model import Base
from app.modules.midagri.model.pg.enums import LoadStatus, text_enum


class PriceLoad(Base):
    """Carga de un mercado. `market_code` es el `BM_Market.code` de SQL Server (sin FK: otra base)."""

    __tablename__ = "price_load"
    __table_args__ = (UniqueConstraint("etl_run_id", "market_code"),)

    etl_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("etl_run.id", ondelete="CASCADE"))
    market_code: Mapped[str] = mapped_column(String(20))
    status: Mapped[LoadStatus] = mapped_column(text_enum(LoadStatus, "load_status"))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    fetched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    matched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    inserted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unmatched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rejected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    """Filas descargadas que no se cargaron por calidad (precio incoherente, sin ubigeo, unidad inválida…)."""
    unmatched_codes: Mapped[list[str] | None] = mapped_column(ARRAY(String(20)))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
