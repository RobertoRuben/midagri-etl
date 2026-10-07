"""`etl_run_event`: el logger de una ejecución (PostgreSQL)."""

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.common.model import Base
from app.modules.midagri.model.pg.enums import EventLevel, text_enum


class EtlRunEvent(Base):
    """Evento de una ejecución: qué pasó, en qué mercado y con qué detalle."""

    __tablename__ = "etl_run_event"
    __table_args__ = (Index("ix_etl_run_event_etl_run_id_id", "etl_run_id", "id"),)

    etl_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("etl_run.id", ondelete="CASCADE"))
    level: Mapped[EventLevel] = mapped_column(text_enum(EventLevel, "event_level"))
    event: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    market_code: Mapped[str | None] = mapped_column(String(20))
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
