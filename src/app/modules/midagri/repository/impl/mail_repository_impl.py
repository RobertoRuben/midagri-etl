"""Destinatarios y registro de envíos (PostgreSQL) y envío por Gmail (SMTP, D37) o Microsoft Graph (D35)."""

import base64
from email.message import EmailMessage
from urllib.parse import quote

import aiosmtplib
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.repository.impl.generic_repository_impl import GenericRepositoryImpl
from app.modules.midagri.model.pg import MailLog, MailRecipient
from app.modules.midagri.model.pg.enums import MailKind
from app.modules.midagri.repository.interface.mail_repository import (
    MailLogRepository,
    MailRecipientRepository,
    MailSender,
    MailSendError,
)

LOGIN_URL = "https://login.microsoftonline.com"
GRAPH_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"


class MailRecipientRepositoryImpl(GenericRepositoryImpl[MailRecipient], MailRecipientRepository):
    """Destinatarios en PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(MailRecipient, session)

    async def list_ordered(self) -> list[MailRecipient]:
        stmt = select(MailRecipient).order_by(MailRecipient.active.desc(), MailRecipient.email)
        return list(await self.session.scalars(stmt))

    async def list_for(self, kind: MailKind) -> list[MailRecipient]:
        flag = {
            MailKind.START: MailRecipient.notify_start,
            MailKind.END: MailRecipient.notify_end,
            MailKind.ERROR: MailRecipient.notify_error,
        }[kind]
        stmt = select(MailRecipient).where(MailRecipient.active, flag).order_by(MailRecipient.email)
        return list(await self.session.scalars(stmt))


class MailLogRepositoryImpl(GenericRepositoryImpl[MailLog], MailLogRepository):
    """Registro de envíos en PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(MailLog, session)

    async def list_by_run(self, etl_run_id: int) -> list[MailLog]:
        stmt = select(MailLog).where(MailLog.etl_run_id == etl_run_id).order_by(MailLog.id)
        return list(await self.session.scalars(stmt))


class GmailSmtpSenderImpl(MailSender):
    """Envío por el SMTP de Gmail con una contraseña de aplicación (D37).

    STARTTLS en el puerto 587. `aiosmtplib` toma los destinatarios de `To` y `Bcc` y quita `Bcc` antes de enviar,
    así nadie ve las direcciones de los demás. Una conexión por correo (son pocos por ejecución).
    """

    def __init__(
        self,
        *,
        username: str | None,
        password: str | None,
        host: str = "smtp.gmail.com",
        port: int = 587,
        timeout_seconds: float = 30,
    ) -> None:
        """Configura el envío.

        Args:
            username: Cuenta de Gmail que se autentica.
            password: Contraseña de aplicación (Google la muestra en grupos de 4 con espacios; se quitan).
            host: Servidor SMTP.
            port: Puerto con STARTTLS.
            timeout_seconds: Tiempo máximo por operación.
        """
        self._username = username
        self._password = "".join(password.split()) if password else None
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds

    async def send(self, message: EmailMessage) -> None:
        missing = [
            name
            for name, value in (("MIDAGRI_MAIL_USERNAME", self._username), ("MIDAGRI_MAIL_PASSWORD", self._password))
            if not value
        ]
        if missing:
            raise ValueError(f"Falta configurar el correo: {', '.join(missing)}")
        try:
            await aiosmtplib.send(
                message,
                hostname=self._host,
                port=self._port,
                start_tls=True,
                username=self._username,
                password=self._password,
                timeout=self._timeout_seconds,
            )
        except aiosmtplib.SMTPAuthenticationError as error:
            raise MailSendError("Autenticación", error.code, "smtp_auth", _smtp_message(error)) from None
        except aiosmtplib.SMTPResponseException as error:
            raise MailSendError("Envío", error.code, "smtp", _smtp_message(error)) from None


def _smtp_message(error: aiosmtplib.SMTPResponseException, limit: int = 300) -> str:
    """Primera línea de la respuesta del servidor (nunca incluye la contraseña)."""
    return (str(error.message).splitlines() or [""])[0][:limit]


class GraphMailSenderImpl(MailSender):
    """Envío por Microsoft Graph desde un buzón de Microsoft 365 (D35).

    Usa una app de Entra ID con el permiso de aplicación `Mail.Send` (client credentials). El correo viaja como
    MIME en base64 a `/users/{mail_from}/sendMail`, así se conservan HTML, texto, `Bcc` y adjunto tal como los
    arma el service. El token se pide en cada envío (son dos por ejecución).
    """

    def __init__(
        self,
        *,
        tenant_id: str | None,
        client_id: str | None,
        client_secret: str | None,
        mail_from: str | None,
        timeout_seconds: float = 30,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Configura el envío.

        Args:
            tenant_id: Id del tenant de Entra ID.
            client_id: Id de la app registrada.
            client_secret: Secreto de la app.
            mail_from: Buzón remitente (UPN o correo).
            timeout_seconds: Tiempo máximo por solicitud.
            client: Cliente HTTP ajeno (tests); si falta, se crea uno por envío.
        """
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._mail_from = mail_from
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def send(self, message: EmailMessage) -> None:
        missing = [name for name, value in self._settings().items() if not value]
        if missing:
            raise ValueError(f"Falta configurar el correo: {', '.join(missing)}")
        if self._client is not None:
            await self._send(self._client, message)
            return
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            await self._send(client, message)

    def _settings(self) -> dict[str, str | None]:
        return {
            "MIDAGRI_MAIL_TENANT_ID": self._tenant_id,
            "MIDAGRI_MAIL_CLIENT_ID": self._client_id,
            "MIDAGRI_MAIL_CLIENT_SECRET": self._client_secret,
            "MIDAGRI_MAIL_FROM": self._mail_from,
        }

    async def _send(self, client: httpx.AsyncClient, message: EmailMessage) -> None:
        token = await self._token(client)
        response = await client.post(
            f"{GRAPH_URL}/users/{quote(str(self._mail_from))}/sendMail",
            content=base64.b64encode(message.as_bytes()),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
            timeout=self._timeout_seconds,
        )
        if not response.is_success:
            raise MailSendError("Envío", response.status_code, *_error_detail(response))

    async def _token(self, client: httpx.AsyncClient) -> str:
        response = await client.post(
            f"{LOGIN_URL}/{quote(str(self._tenant_id))}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": str(self._client_id),
                "client_secret": str(self._client_secret),
                "scope": GRAPH_SCOPE,
            },
            timeout=self._timeout_seconds,
        )
        if not response.is_success:
            raise MailSendError("Token", response.status_code, *_error_detail(response))
        return response.json()["access_token"]


def _error_detail(response: httpx.Response, limit: int = 300) -> tuple[str, str]:
    """Código y mensaje de un error de Entra ID (`error`, `error_description`) o de Graph (`error.code`, `.message`)."""
    try:
        body = response.json()
    except ValueError:
        return "sin_codigo", response.text[:limit]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("code", "sin_codigo")), str(error.get("message", ""))[:limit]
    if isinstance(error, str):
        description = str(body.get("error_description") or "")
        return error, (description.splitlines() or [""])[0][:limit]
    return "sin_codigo", response.text[:limit]
