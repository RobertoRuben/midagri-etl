"""Respuestas de los destinatarios de correo."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MailRecipientResponse(BaseModel):
    """Destinatario de los correos del ETL."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str | None = None
    notify_start: bool
    notify_end: bool
    notify_error: bool
    active: bool
    created_at: datetime
    updated_at: datetime
