"""`mail_recipient`: destinatarios de los correos del ETL (PostgreSQL, D25)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.common.model import Base


class MailRecipient(Base):
    """Destinatario. No se borra: se desactiva con `active=False`."""

    __tablename__ = "mail_recipient"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str | None] = mapped_column(String(120))
    notify_start: Mapped[bool] = mapped_column(default=True, server_default="true")
    notify_end: Mapped[bool] = mapped_column(default=True, server_default="true")
    notify_error: Mapped[bool] = mapped_column(default=True, server_default="true")
    """Recibe el correo de incidencias (errores y advertencias con su log, D37)."""
    active: Mapped[bool] = mapped_column(default=True, server_default="true")
