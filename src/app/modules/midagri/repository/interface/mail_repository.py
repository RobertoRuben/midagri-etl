"""Contratos de los destinatarios, el registro de envíos y el envío de los correos."""

from email.message import EmailMessage
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.repository.interface.generic_repository import GenericRepository
from app.modules.midagri.model.pg import MailLog, MailRecipient
from app.modules.midagri.model.pg.enums import MailKind


class MailRecipientRepository(GenericRepository[MailRecipient], Protocol):
    """Destinatarios (PostgreSQL)."""

    async def list_ordered(self) -> list[MailRecipient]:
        """Todos los destinatarios, activos primero y por correo."""
        ...

    async def list_for(self, kind: MailKind) -> list[MailRecipient]:
        """Destinatarios activos que reciben el correo de ese tipo (inicio, fin o incidencias)."""
        ...


class MailLogRepository(GenericRepository[MailLog], Protocol):
    """Registro de envíos (PostgreSQL)."""

    session: AsyncSession

    async def list_by_run(self, etl_run_id: int) -> list[MailLog]:
        """Correos de una ejecución, en orden."""
        ...


class MailSendError(RuntimeError):
    """El proveedor de correo rechazó la autenticación o el envío.

    Attributes:
        status_code: Código de respuesta: SMTP (p. ej. 535) o HTTP (Graph).
        code: Código de error del proveedor (p. ej. `smtp_auth`, `ErrorAccessDenied`, `invalid_client`).
    """

    def __init__(self, step: str, status_code: int, code: str, detail: str) -> None:
        super().__init__(f"{step} rechazado ({status_code} {code}): {detail}")
        self.status_code = status_code
        self.code = code


class MailSender(Protocol):
    """Envío de un correo ya armado."""

    async def send(self, message: EmailMessage) -> None:
        """Envía el correo.

        Raises:
            MailSendError: Si el proveedor rechaza la autenticación o el envío.
            httpx.HTTPError: Graph: sin conexión o tiempo agotado.
            OSError: Gmail: sin conexión o tiempo agotado (`aiosmtplib.SMTPConnectError`, `SMTPTimeoutError`).
        """
        ...
