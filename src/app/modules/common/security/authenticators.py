"""Puertos de autenticación implementados fuera de `common` (SPEC-tenant §3.6).

`iam` implementa `BearerAuthenticator` y `api-key` implementa `ApiKeyAuthenticator`;
`main.py` los registra como implementaciones de `get_bearer_authenticator` y
`get_api_key_authenticator`. `common` nunca importa dichos módulos.
"""

from typing import Protocol

from app.modules.common.security.auth_context import AuthContext
from app.modules.common.security.current_user import CurrentUser


class BearerAuthenticator(Protocol):
    """Convierte un access token JWT en la persona autenticada. Implementado por `iam`."""

    async def authenticate(self, token: str) -> CurrentUser:
        """Verifica el `token` y retorna la persona a la que pertenece.

        Args:
            token: Access token en texto plano, sin el prefijo `Bearer`.

        Returns:
            La persona autenticada (`CurrentUser`).

        Raises:
            UnauthorizedException: Si el token está mal formado, expirado o con firma inválida.
        """
        ...


class ApiKeyAuthenticator(Protocol):
    """Convierte un `X-API-Key` sin procesar en la identidad del tenant otorgada. Implementado por `api-key`."""

    async def authenticate(self, raw_key: str) -> AuthContext:
        """Verifica `raw_key` y retorna su identidad de tenant.

        Args:
            raw_key: Secreto tal como se recibió en la cabecera `X-API-Key`.

        Returns:
            Un `AuthContext` con `tenant_id` y `api_key_id`.

        Raises:
            UnauthorizedException: Si la clave no existe, fue revocada o expiró.
        """
        ...


class AuthenticatorNotRegisteredError(RuntimeError):
    """Error emitido cuando se ejecuta una dependencia de autenticación sin implementación en `main.py`.

    Representa un error de despliegue y no de cliente, por lo que deliberadamente no es
    `ProblemDetailsException`: el manejador genérico responderá 500 sin detalles internos
    y registrará este mensaje con su traza. La solicitud nunca es autorizada.

    Attributes:
        port: Protocolo que carece de implementación registrada.
        factory: Dependencia de fábrica que `main.py` debe registrar.
    """

    def __init__(self, port: str, factory: str) -> None:
        self.port = port
        self.factory = factory
        super().__init__(
            f"No {port} is registered: main.py must provide an implementation for `{factory}`. "
            "Refusing to authenticate."
        )
