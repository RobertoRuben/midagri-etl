"""Contratos de los correos de una ejecución y de la administración de destinatarios."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.modules.midagri.dto.request.mail_recipient_request import (
    MailRecipientCreateRequest,
    MailRecipientUpdateRequest,
)
from app.modules.midagri.dto.response.etl_run_response import EtlRunDetailResponse, LogEventResponse
from app.modules.midagri.dto.response.mail_recipient_response import MailRecipientResponse
from app.modules.midagri.model.pg.enums import MailStatus


@dataclass(frozen=True, slots=True)
class MailAttachment:
    """Archivo adjunto (p. ej. el Excel de faltantes)."""

    filename: str
    content: bytes
    mime_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class NotificationService(ABC):
    """Correos de inicio, fin e incidencias de una ejecución. **Nunca** lanza: un fallo de envío no tumba el ETL."""

    @abstractmethod
    async def notify_start(
        self, run: EtlRunDetailResponse, *, market_names: Mapping[str, str] | None = None
    ) -> MailStatus:
        """Envía el correo de inicio a quienes tienen `notify_start` y lo registra en `mail_log`."""

    @abstractmethod
    async def notify_end(
        self,
        run: EtlRunDetailResponse,
        attachment: MailAttachment | None = None,
        *,
        market_names: Mapping[str, str] | None = None,
    ) -> MailStatus:
        """Envía el correo de fin con el Excel si se generó y lo registra en `mail_log`."""

    @abstractmethod
    async def notify_errors(
        self,
        run: EtlRunDetailResponse,
        events: Sequence[LogEventResponse],
        *,
        market_names: Mapping[str, str] | None = None,
    ) -> MailStatus:
        """Envía el correo de incidencias (D37) con el log de errores y advertencias y sus trazas.

        Lo reciben quienes tienen `notify_error`. El llamador lo invoca solo si `events` no está vacío.
        """


class MailRecipientService(ABC):
    """Administración de los destinatarios de correo."""

    @abstractmethod
    async def list_all(self) -> list[MailRecipientResponse]:
        """Todos los destinatarios, activos primero."""

    @abstractmethod
    async def create(self, request: MailRecipientCreateRequest) -> MailRecipientResponse:
        """Agrega un destinatario.

        Raises:
            ConflictException: Si el correo ya está registrado.
        """

    @abstractmethod
    async def update(self, recipient_id: int, request: MailRecipientUpdateRequest) -> MailRecipientResponse:
        """Cambia los campos enviados de un destinatario.

        Raises:
            NotFoundException: Si el destinatario no existe.
        """
