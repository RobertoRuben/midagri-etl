"""Módulo para definición y validación de tipos de archivos fotográficos subidos."""

from typing import Annotated, Final

from fastapi import Depends, UploadFile
from pydantic import WithJsonSchema

from app.modules.common.config import base_config
from app.modules.common.exception import BadRequestException, UnprocessableEntityException

UploadedPhoto = Annotated[
    UploadFile,
    WithJsonSchema({"type": "string", "format": "binary"}),
]
"""Tipo anotado para archivos de foto subidos, representado como binario en OpenAPI."""

ALLOWED_CONTENT_TYPES: Final[tuple[str, ...]] = (
    "image/jpeg",
    "image/jpg",
    "image/png",
)
"""Tipos MIME permitidos para la carga de imágenes."""


def validated_photo(photo: UploadedPhoto) -> UploadFile:
    """Valida el tipo MIME y el tamaño de la foto subida.

    Args:
        photo: Archivo de foto enviado en la solicitud.

    Returns:
        El mismo archivo validado si cumple con las restricciones.

    Raises:
        UnprocessableEntityException: Si el tipo MIME no está permitido.
        BadRequestException: Si el tamaño excede el límite configurado.
    """
    if photo.content_type not in ALLOWED_CONTENT_TYPES:
        raise UnprocessableEntityException(
            f"photo must be one of {', '.join(ALLOWED_CONTENT_TYPES)}",
        )

    max_bytes = base_config.max_photo_bytes
    if photo.size is not None and photo.size > max_bytes:
        raise BadRequestException(
            f"photo must not exceed {max_bytes} bytes",
        )
    return photo


ValidatedPhotoDep = Annotated[UploadFile, Depends(validated_photo)]
