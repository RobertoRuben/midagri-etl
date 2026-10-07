"""Tipos validados y utilidades de validación compartidas del sistema."""

from app.modules.common.types.api_responses import (
    LOOKUP_AUTH_RESPONSES,
    SUPER_ADMIN_REQUIRED_RESPONSE,
    TENANT_ADMIN_REQUIRED_RESPONSE,
    UNAUTHORIZED_BEARER_RESPONSE,
    VALIDATION_RESPONSE,
    ResponsesDict,
    problem_response,
    role_required_response,
)
from app.modules.common.types.openapi import TagMetadata
from app.modules.common.types.upload_types import (
    ALLOWED_CONTENT_TYPES,
    UploadedPhoto,
    ValidatedPhotoDep,
    validated_photo,
)

__all__: list[str] = [
    "ALLOWED_CONTENT_TYPES",
    "LOOKUP_AUTH_RESPONSES",
    "ResponsesDict",
    "SUPER_ADMIN_REQUIRED_RESPONSE",
    "TENANT_ADMIN_REQUIRED_RESPONSE",
    "TagMetadata",
    "UNAUTHORIZED_BEARER_RESPONSE",
    "UploadedPhoto",
    "VALIDATION_RESPONSE",
    "ValidatedPhotoDep",
    "problem_response",
    "role_required_response",
    "validated_photo",
]
