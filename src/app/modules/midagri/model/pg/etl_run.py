"""`etl_run`: una fila por ejecución del ETL (PostgreSQL)."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, String, Text, literal_column
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.common.model import Base
from app.modules.midagri.model.pg.enums import ACTIVE_RUN_STATUSES, RunStatus, RunTrigger, text_enum

_ACTIVE = ", ".join(f"'{status.value}'" for status in ACTIVE_RUN_STATUSES)


class EtlRun(Base):
    """Ejecución del ETL. Solo puede haber una `queued` o `running` a la vez (`uq_etl_run_active`)."""

    __tablename__ = "etl_run"
    __table_args__ = (
        Index(
            "uq_etl_run_active",
            literal_column("(true)"),
            unique=True,
            postgresql_where=literal_column(f"status IN ({_ACTIVE})"),
        ),
        Index("ix_etl_run_created_at", literal_column("created_at DESC")),
    )

    status: Mapped[RunStatus] = mapped_column(text_enum(RunStatus, "run_status"), default=RunStatus.QUEUED)
    trigger: Mapped[RunTrigger] = mapped_column(text_enum(RunTrigger, "run_trigger"))
    requested_by: Mapped[str | None] = mapped_column(String(120))
    dry_run: Mapped[bool] = mapped_column(default=False, server_default="false")
    """Ejecución de prueba: descarga, valida y cuenta, pero no escribe en SQL Server."""
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    market_codes: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    fetched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    matched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    inserted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unmatched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rejected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    """Filas descargadas que no se cargaron por calidad (precio incoherente, sin ubigeo, unidad inválida…)."""
    gaps_esc1: Mapped[int | None] = mapped_column(Integer)
    gaps_esc2: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
