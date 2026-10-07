"""Solicitudes para administrar los destinatarios de correo."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field


def _lower(value: str) -> str:
    return value.strip().lower()


NormalizedEmail = Annotated[EmailStr, AfterValidator(_lower)]
"""Correo válido, sin espacios y en minúsculas (así se guarda y se compara)."""


class MailRecipientCreateRequest(BaseModel):
    """Alta de un destinatario."""

    email: NormalizedEmail
    name: str | None = Field(default=None, max_length=120)
    notify_start: bool = True
    notify_end: bool = True
    notify_error: bool = True
    """Recibe el correo de incidencias con el log de errores y advertencias (D37)."""


class MailRecipientUpdateRequest(BaseModel):
    """Cambio parcial de un destinatario: solo se aplican los campos enviados. No se borra: se desactiva."""

    name: str | None = Field(default=None, max_length=120)
    notify_start: bool | None = None
    notify_end: bool | None = None
    notify_error: bool | None = None
    active: bool | None = None
