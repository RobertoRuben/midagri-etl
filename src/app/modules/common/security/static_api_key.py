"""Autenticación del MVP: una sola `X-API-Key` definida en `.env` (`MIDAGRI_API_KEY`, D24).

Después del MVP, `iam` implementa `ApiKeyAuthenticator` con claves en PostgreSQL; los routers siguen
dependiendo de `require_api_key`, así que no cambian.
"""

import hmac
from typing import Annotated, Final

from fastapi import Depends, status
from fastapi.security import APIKeyHeader

from app.modules.common.config import base_config
from app.modules.common.exception import UnauthorizedException
from app.modules.common.types.api_responses import ResponsesDict, problem_response

API_KEY_HEADER: Final[str] = "X-API-Key"

_api_key_header = APIKeyHeader(
    name=API_KEY_HEADER,
    scheme_name="ApiKey",
    description="Clave de la API (`MIDAGRI_API_KEY`). La usa la tarea programada y soporte.",
    auto_error=False,
)

API_KEY_RESPONSES: ResponsesDict = {
    status.HTTP_401_UNAUTHORIZED: problem_response("Falta la cabecera X-API-Key o no es válida."),
}
"""Respuesta 401 para documentar en OpenAPI los routers protegidos."""


async def require_api_key(api_key: Annotated[str | None, Depends(_api_key_header)]) -> None:
    """Exige la `X-API-Key` correcta. Compara en tiempo constante (`hmac.compare_digest`).

    Raises:
        UnauthorizedException: Si falta la cabecera o la clave no coincide.
    """
    expected = base_config.api_key.get_secret_value()
    if api_key is None or not hmac.compare_digest(api_key.encode(), expected.encode()):
        raise UnauthorizedException("Falta la cabecera X-API-Key o no es válida.")
