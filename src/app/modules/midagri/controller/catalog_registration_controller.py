"""`/catalog/registrations`: subir la hoja `Registro` del Excel de faltantes y registrar sus productos (D33)."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, Request, UploadFile, status

from app.modules.common.exception import PayloadTooLargeException
from app.modules.common.pagination.paginated import Paginated
from app.modules.common.security.static_api_key import API_KEY_RESPONSES, require_api_key
from app.modules.common.types.api_responses import problem_response
from app.modules.common.types.openapi import TagMetadata
from app.modules.midagri.dto.response.catalog_registration_response import (
    CatalogRegistrationResponse,
    CatalogRegistrationSummaryResponse,
)
from app.modules.midagri.service.dependencies.catalog_registration_deps import CatalogRegistrationServiceDep

MAX_FILE_BYTES = 5 * 1024 * 1024

TAG: TagMetadata = {
    "name": "catalog-registrations",
    "description": (
        "Registra los productos faltantes: se sube el Excel del correo (se lee la hoja `Registro`). "
        "Por defecto es `dry_run`: valida y muestra qué se haría sin escribir."
    ),
}

router = APIRouter(
    prefix="/catalog/registrations",
    tags=["catalog-registrations"],
    dependencies=[Depends(require_api_key)],
    responses=API_KEY_RESPONSES,
)


@router.post(
    "",
    responses={
        status.HTTP_409_CONFLICT: problem_response("El SP del catálogo reemplaza el código por un correlativo."),
        status.HTTP_413_CONTENT_TOO_LARGE: problem_response("Archivo de más de 5 MB."),
        status.HTTP_422_UNPROCESSABLE_CONTENT: problem_response("Archivo sin la hoja `Registro` o con otras columnas."),
    },
)
async def register(
    service: CatalogRegistrationServiceDep,
    request: Request,
    file: Annotated[UploadFile, File(description="Excel de faltantes (.xlsx) con la hoja `Registro`.")],
    dry_run: Annotated[bool, Form(description="True: solo valida. False: registra.")] = True,
) -> CatalogRegistrationResponse:
    """Valida la hoja `Registro` y, con `dry_run=false`, registra sus productos con el SP del app.

    Si alguna fila es inválida no se registra ninguna. Los códigos que ya están en el catálogo se omiten.
    """
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise PayloadTooLargeException("El archivo supera los 5 MB.")
    return await service.register(
        file.filename or "registro.xlsx",
        content,
        dry_run=dry_run,
        requested_by=request.client.host if request.client else None,
    )


@router.get("")
async def list_registrations(
    service: CatalogRegistrationServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Paginated[CatalogRegistrationSummaryResponse]:
    """Subidas, la más reciente primero."""
    return await service.list_loads(page, size)


@router.get("/{catalog_load_id}", responses={status.HTTP_404_NOT_FOUND: problem_response("La subida no existe.")})
async def get_registration(
    service: CatalogRegistrationServiceDep,
    catalog_load_id: Annotated[int, Path(ge=1, description="Id de la subida")],
) -> CatalogRegistrationResponse:
    """Una subida con el resultado de cada fila."""
    return await service.get_load(catalog_load_id)
