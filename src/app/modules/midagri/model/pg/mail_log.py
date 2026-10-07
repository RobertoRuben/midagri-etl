"""`mail_log`: un registro por correo enviado o intentado (PostgreSQL, D25)."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.common.model import Base
from app.modules.midagri.model.pg.enums import MailKind, MailStatus, text_enum


class MailLog(Base):
    """Correo de inicio, fin o incidencias de una ejecución, con su resultado."""

    __tablename__ = "mail_log"

    etl_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("etl_run.id", ondelete="SET NULL"))
    kind: Mapped[MailKind] = mapped_column(text_enum(MailKind, "mail_kind"))
    subject: Mapped[str] = mapped_column(String(200))
    recipients: Mapped[list[str]] = mapped_column(ARRAY(String(254)))
    status: Mapped[MailStatus] = mapped_column(text_enum(MailStatus, "mail_status"))
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
