"""Dependencias FastAPI de los destinatarios, el registro de envíos (PostgreSQL) y el envío de correos."""

from typing import Annotated

from fastapi import Depends

from app.modules.common.config import base_config
from app.modules.common.db.dependencies import PgSessionDep
from app.modules.midagri.repository.impl.mail_repository_impl import (
    GmailSmtpSenderImpl,
    GraphMailSenderImpl,
    MailLogRepositoryImpl,
    MailRecipientRepositoryImpl,
)
from app.modules.midagri.repository.interface.mail_repository import (
    MailLogRepository,
    MailRecipientRepository,
    MailSender,
)


def get_mail_recipient_repository(session: PgSessionDep) -> MailRecipientRepository:
    """Repositorio de destinatarios."""
    return MailRecipientRepositoryImpl(session)


def get_mail_log_repository(session: PgSessionDep) -> MailLogRepository:
    """Repositorio del registro de envíos (misma sesión que los destinatarios en la misma solicitud)."""
    return MailLogRepositoryImpl(session)


def get_mail_sender() -> MailSender:
    """Envío según `MIDAGRI_MAIL_PROVIDER`: Gmail por SMTP (D37, por defecto) o Microsoft Graph (D35)."""
    if base_config.mail_provider == "gmail":
        password = base_config.mail_password.get_secret_value() if base_config.mail_password else None
        return GmailSmtpSenderImpl(
            username=base_config.mail_username,
            password=password,
            host=base_config.mail_smtp_host,
            port=base_config.mail_smtp_port,
        )
    secret = base_config.mail_client_secret.get_secret_value() if base_config.mail_client_secret else None
    return GraphMailSenderImpl(
        tenant_id=base_config.mail_tenant_id,
        client_id=base_config.mail_client_id,
        client_secret=secret,
        mail_from=base_config.mail_from,
    )


MailRecipientRepositoryDep = Annotated[MailRecipientRepository, Depends(get_mail_recipient_repository)]
MailLogRepositoryDep = Annotated[MailLogRepository, Depends(get_mail_log_repository)]
MailSenderDep = Annotated[MailSender, Depends(get_mail_sender)]
