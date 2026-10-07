"""Fábricas y constantes reutilizables para documentar respuestas de error en OpenAPI."""

from typing import Any

from fastapi import status

from app.modules.common.exception.exception_rfc_schema import ProblemDetailsModel

ResponsesDict = dict[int | str, dict[str, Any]]


def problem_response(description: str) -> dict[str, Any]:
    """Entrada de `responses=` con el esquema RFC 7807 estándar (`ProblemDetailsModel`)."""
    return {"model": ProblemDetailsModel, "description": description}


def role_required_response(role: str) -> ResponsesDict:
    """403 estándar para endpoints que requieren un rol específico."""
    return {status.HTTP_403_FORBIDDEN: problem_response(f"La operación requiere el rol `{role}`.")}


UNAUTHORIZED_BEARER_RESPONSE: ResponsesDict = {
    status.HTTP_401_UNAUTHORIZED: problem_response("No se proporcionó un access token Bearer válido."),
}

SUPER_ADMIN_REQUIRED_RESPONSE: ResponsesDict = role_required_response("super_admin")
TENANT_ADMIN_REQUIRED_RESPONSE: ResponsesDict = role_required_response("tenant_admin")

VALIDATION_RESPONSE: ResponsesDict = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: problem_response("La solicitud contiene parámetros o campos inválidos."),
}

LOOKUP_AUTH_RESPONSES: ResponsesDict = {
    status.HTTP_400_BAD_REQUEST: problem_response("Se envió JWT y X-API-Key a la vez; use solo una credencial."),
    status.HTTP_401_UNAUTHORIZED: problem_response("Falta un JWT Bearer o un X-API-Key válido."),
    status.HTTP_403_FORBIDDEN: problem_response("Un superadministrador no puede consumir el API comercial."),
    status.HTTP_429_TOO_MANY_REQUESTS: problem_response("Se superó el límite de solicitudes del tenant."),
}
