"""Correos del ETL (Microsoft Graph) y administración de destinatarios (PostgreSQL)."""

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy.exc import IntegrityError

from app.modules.common.db.decorator.transactional import transactional
from app.modules.common.exception import ConflictException, NotFoundException
from app.modules.midagri.dto.request.mail_recipient_request import (
    MailRecipientCreateRequest,
    MailRecipientUpdateRequest,
)
from app.modules.midagri.dto.response.etl_run_response import EtlRunDetailResponse, LogEventResponse
from app.modules.midagri.dto.response.mail_recipient_response import MailRecipientResponse
from app.modules.midagri.model.pg import MailLog, MailRecipient
from app.modules.midagri.model.pg.enums import MailKind, MailStatus
from app.modules.midagri.repository.interface.mail_repository import (
    MailLogRepository,
    MailRecipientRepository,
    MailSender,
)
from app.modules.midagri.service.interface.notification_service import (
    MailAttachment,
    MailRecipientService,
    NotificationService,
)
from app.modules.midagri.utils.mail_templates import MailContent, build_end_mail, build_error_mail, build_start_mail

logger = logging.getLogger(__name__)


class EmailNotificationServiceImpl(NotificationService):
    """Envía los correos de una ejecución y registra cada intento en `mail_log`.

    Un solo correo por tipo, con todos los destinatarios en `Bcc`. Si el envío o el registro fallan, se
    anota en el log de la aplicación y se devuelve el estado: el ETL nunca se cae por un correo.

    Args:
        recipient_repository: Destinatarios (misma sesión de PostgreSQL que `mail_log_repository`).
        mail_log_repository: Registro de envíos.
        sender: Envío de correos (Microsoft Graph).
        enabled: `MIDAGRI_MAIL_ENABLED`; si es False, se registra `skipped` y no se envía nada.
        mail_from: Remitente (el buzón de Microsoft 365 de `MIDAGRI_MAIL_FROM`).
        api_public_url: Base de los enlaces al log.
        catalog_auto_register: Si el ETL registra solo los faltantes (D36); cambia la indicación del adjunto.
    """

    __session_attr__ = "mail_log_repository.session"

    def __init__(
        self,
        recipient_repository: MailRecipientRepository,
        mail_log_repository: MailLogRepository,
        sender: MailSender,
        *,
        enabled: bool,
        mail_from: str | None,
        api_public_url: str,
        catalog_auto_register: bool = False,
    ) -> None:
        self.recipient_repository = recipient_repository
        self.mail_log_repository = mail_log_repository
        self.sender = sender
        self.enabled = enabled
        self.mail_from = mail_from
        self.api_public_url = api_public_url.rstrip("/")
        self.catalog_auto_register = catalog_auto_register

    async def notify_start(
        self, run: EtlRunDetailResponse, *, market_names: Mapping[str, str] | None = None
    ) -> MailStatus:
        return await self._notify(
            run, MailKind.START, build_start_mail(run, market_names=market_names), attachment=None
        )

    async def notify_end(
        self,
        run: EtlRunDetailResponse,
        attachment: MailAttachment | None = None,
        *,
        market_names: Mapping[str, str] | None = None,
    ) -> MailStatus:
        content = build_end_mail(
            run,
            logs_url=f"{self.api_public_url}/etl/runs/{run.id}/logs",
            has_attachment=attachment is not None,
            market_names=market_names,
            auto_register=self.catalog_auto_register,
        )
        return await self._notify(run, MailKind.END, content, attachment=attachment)

    async def notify_errors(
        self,
        run: EtlRunDetailResponse,
        events: Sequence[LogEventResponse],
        *,
        market_names: Mapping[str, str] | None = None,
    ) -> MailStatus:
        content = build_error_mail(
            run,
            events,
            logs_url=f"{self.api_public_url}/etl/runs/{run.id}/logs",
            market_names=market_names,
        )
        return await self._notify(run, MailKind.ERROR, content, attachment=None)

    async def _notify(
        self, run: EtlRunDetailResponse, kind: MailKind, content: MailContent, *, attachment: MailAttachment | None
    ) -> MailStatus:
        recipients: list[str] = []
        status, error, sent_at = MailStatus.SKIPPED, None, None
        if not self.enabled:
            error = "Envío de correos desactivado (MIDAGRI_MAIL_ENABLED=false)."
        else:
            try:
                recipients = [recipient.email for recipient in await self.recipient_repository.list_for(kind)]
            except Exception as exc:
                status, error = MailStatus.FAILED, f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "No se pudieron consultar destinatarios para %s de la ejecución %s: %s", kind.value, run.id, error
                )
                try:
                    await self.mail_log_repository.session.rollback()
                except Exception:
                    logger.exception("No se pudo revertir la consulta de destinatarios de la ejecución %s", run.id)
            else:
                if not recipients:
                    error = f"No hay destinatarios activos para el correo de {kind.value}."
                else:
                    try:
                        await self.sender.send(self._message(content, recipients, attachment))
                        status, sent_at = MailStatus.SENT, datetime.now(UTC)
                    except Exception as exc:  # un correo nunca tumba el ETL
                        status, error = MailStatus.FAILED, f"{type(exc).__name__}: {exc}"
                        logger.warning("Correo de %s de la ejecución %s no enviado: %s", kind.value, run.id, error)
        try:
            await self._record(run.id, kind, content.subject, recipients, status, error, sent_at)
        except Exception:
            logger.exception("No se pudo registrar en mail_log el correo de %s de la ejecución %s", kind.value, run.id)
        return status

    @transactional
    async def _record(
        self,
        etl_run_id: int,
        kind: MailKind,
        subject: str,
        recipients: list[str],
        status: MailStatus,
        error: str | None,
        sent_at: datetime | None,
    ) -> None:
        await self.mail_log_repository.save(
            MailLog(
                etl_run_id=etl_run_id,
                kind=kind,
                subject=subject,
                recipients=recipients,
                status=status,
                error=error,
                sent_at=sent_at,
            )
        )

    def _message(self, content: MailContent, recipients: list[str], attachment: MailAttachment | None) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = content.subject
        message["From"] = self.mail_from or ""
        message["To"] = self.mail_from or ""
        message["Bcc"] = ", ".join(recipients)
        message.set_content(content.text)
        message.add_alternative(content.html, subtype="html")
        if attachment is not None:
            maintype, subtype = attachment.mime_type.split("/", 1)
            message.add_attachment(attachment.content, maintype=maintype, subtype=subtype, filename=attachment.filename)
        return message


class MailRecipientServiceImpl(MailRecipientService):
    """Alta, consulta y cambio de destinatarios."""

    __session_attr__ = "recipient_repository.session"

    def __init__(self, recipient_repository: MailRecipientRepository) -> None:
        self.recipient_repository = recipient_repository

    async def list_all(self) -> list[MailRecipientResponse]:
        recipients = await self.recipient_repository.list_ordered()
        return [MailRecipientResponse.model_validate(recipient) for recipient in recipients]

    @transactional
    async def create(self, request: MailRecipientCreateRequest) -> MailRecipientResponse:
        if await self.recipient_repository.exist_by(MailRecipient.email, request.email):
            raise ConflictException(f"El correo {request.email} ya está registrado.")
        try:
            recipient = await self.recipient_repository.save(MailRecipient(**request.model_dump()))
        except IntegrityError as exc:  # alta simultánea del mismo correo
            raise ConflictException(f"El correo {request.email} ya está registrado.") from exc
        return MailRecipientResponse.model_validate(recipient)

    @transactional
    async def update(self, recipient_id: int, request: MailRecipientUpdateRequest) -> MailRecipientResponse:
        recipient = await self.recipient_repository.get_by_id(recipient_id)
        if recipient is None:
            raise NotFoundException(f"No existe el destinatario {recipient_id}.")
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(recipient, field, value)
        saved = await self.recipient_repository.save(recipient)
        return MailRecipientResponse.model_validate(saved)
