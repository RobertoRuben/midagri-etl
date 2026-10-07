"""Dependencias FastAPI de los services de correo."""

from typing import Annotated

from fastapi import Depends

from app.modules.common.config import base_config
from app.modules.midagri.repository.dependencies.mail_repository_deps import (
    MailLogRepositoryDep,
    MailRecipientRepositoryDep,
    MailSenderDep,
)
from app.modules.midagri.service.impl.notification_service_impl import (
    EmailNotificationServiceImpl,
    MailRecipientServiceImpl,
)
from app.modules.midagri.service.interface.notification_service import MailRecipientService, NotificationService


def get_notification_service(
    recipients: MailRecipientRepositoryDep, mail_log: MailLogRepositoryDep, sender: MailSenderDep
) -> NotificationService:
    """Correos de inicio y fin de una ejecución."""
    return EmailNotificationServiceImpl(
        recipients,
        mail_log,
        sender,
        enabled=base_config.mail_enabled,
        mail_from=base_config.mail_from,
        api_public_url=base_config.api_public_url,
        catalog_auto_register=base_config.catalog_auto_register,
    )


def get_mail_recipient_service(recipients: MailRecipientRepositoryDep) -> MailRecipientService:
    """Administración de destinatarios."""
    return MailRecipientServiceImpl(recipients)


NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
MailRecipientServiceDep = Annotated[MailRecipientService, Depends(get_mail_recipient_service)]
