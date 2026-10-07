"""`/notifications/recipients`: destinatarios de los correos del ETL (D25)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.modules.common.security.static_api_key import API_KEY_RESPONSES, require_api_key
from app.modules.common.types.api_responses import problem_response
from app.modules.common.types.openapi import TagMetadata
from app.modules.midagri.dto.request.mail_recipient_request import (
    MailRecipientCreateRequest,
    MailRecipientUpdateRequest,
)
from app.modules.midagri.dto.response.mail_recipient_response import MailRecipientResponse
from app.modules.midagri.service.dependencies.notification_deps import MailRecipientServiceDep

TAG: TagMetadata = {
    "name": "notifications",
    "description": "Destinatarios de los correos de inicio y fin. No se borran: se desactivan.",
}

router = APIRouter(
    prefix="/notifications/recipients",
    tags=["notifications"],
    dependencies=[Depends(require_api_key)],
    responses=API_KEY_RESPONSES,
)


@router.get("")
async def list_recipients(service: MailRecipientServiceDep) -> list[MailRecipientResponse]:
    """Todos los destinatarios, activos primero."""
    return await service.list_all()


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: problem_response("El correo ya está registrado.")},
)
async def create_recipient(
    service: MailRecipientServiceDep, request: MailRecipientCreateRequest
) -> MailRecipientResponse:
    """Agrega un destinatario."""
    return await service.create(request)


@router.patch(
    "/{recipient_id}",
    responses={status.HTTP_404_NOT_FOUND: problem_response("El destinatario no existe.")},
)
async def update_recipient(
    service: MailRecipientServiceDep,
    recipient_id: Annotated[int, Path(ge=1)],
    request: MailRecipientUpdateRequest,
) -> MailRecipientResponse:
    """Cambia nombre, `notify_start`, `notify_end` o `active` (solo los campos enviados)."""
    return await service.update(recipient_id, request)
