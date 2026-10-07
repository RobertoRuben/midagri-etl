"""`gap_report`: reportes de faltantes ya calculados, con su Excel (PostgreSQL)."""

from datetime import date
from typing import Any

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, LargeBinary, String, literal_column
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.common.model import Base


class GapReport(Base):
    """Reporte de faltantes (ESC1/ESC2) de una ejecución del ETL o de un recálculo a pedido.

    Se calcula con los precios que la ingesta ya descargó, así que no hace consultas extra al portal.
    `GET /catalog/gaps` y `/excel` devuelven el último, al instante; el correo de fin adjunta su Excel.
    """

    __tablename__ = "gap_report"
    __table_args__ = (Index("ix_gap_report_created_at", literal_column("created_at DESC")),)

    etl_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("etl_run.id", ondelete="SET NULL"))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    markets: Mapped[list[str]] = mapped_column(ARRAY(String(120)))
    total_esc1: Mapped[int] = mapped_column(Integer)
    total_esc2: Mapped[int] = mapped_column(Integer)
    warnings: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    """`GapReportResponse` completo (`model_dump(mode="json")`)."""
    excel_filename: Mapped[str] = mapped_column(String(80))
    excel: Mapped[bytes] = mapped_column(LargeBinary)
