"""Dependencias FastAPI del contrato de autenticación (SPEC-tenant §3.6, SPEC-iam §3.4 y §4).

Leen las credenciales, aplican las reglas de credencial dual y la jerarquía de roles,
y delegan la verificación real a `BearerAuthenticator` y `ApiKeyAuthenticator`
que `main.py` registra para `get_bearer_authenticator` y `get_api_key_authenticator`.

Aquí vive también la fábrica del tercer puerto del mismo patrón, `TenantSessionRevoker`
(`session_revoker.py`): no autentica, pero se registra igual — `common` declara el contrato,
`iam` lo implementa y `main.py` los conecta (SPEC-tenant §3.6).
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Final

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

from app.modules.common.exception import BadRequestException, ForbiddenException, UnauthorizedException
from app.modules.common.security.auth_context import AuthContext
from app.modules.common.security.authenticators import (
    ApiKeyAuthenticator,
    AuthenticatorNotRegisteredError,
    BearerAuthenticator,
)
from app.modules.common.security.current_user import CurrentUser
from app.modules.common.security.session_revoker import SessionRevokerNotRegisteredError, TenantSessionRevoker
from app.modules.common.security.user_role import UserRole

API_KEY_HEADER: Final[str] = "X-API-Key"
"""Cabecera HTTP que porta el API key del tenant."""

_ROLE_RANK: Final[dict[UserRole, int]] = {
    UserRole.TENANT_MEMBER: 0,
    UserRole.TENANT_ADMIN: 1,
    UserRole.SUPER_ADMIN: 2,
}

_TENANT_ROLES: Final[frozenset[UserRole]] = frozenset({UserRole.TENANT_ADMIN, UserRole.TENANT_MEMBER})

_bearer_scheme = OAuth2PasswordBearer(
    tokenUrl="api/v1/auth/login",
    scheme_name="OAuth2PasswordBearer",
    description="Access token JWT obtenido en `POST /api/v1/auth/login`.",
    auto_error=False,
)
_api_key_scheme = APIKeyHeader(
    name=API_KEY_HEADER,
    scheme_name="ApiKey",
    description="API key del tenant. Solo en rutas de nivel tenant y nunca junto con un JWT.",
    auto_error=False,
)


async def get_bearer_authenticator() -> BearerAuthenticator:
    """Retorna el autenticador JWT registrado por `main.py`.

    `common` no posee implementación: `main.py` sobreescribe esta dependencia con la provista por
    `iam`. Mientras no se registre, cualquier ruta que autentique a una persona fallará.

    Raises:
        AuthenticatorNotRegisteredError: Siempre, a menos que la dependencia sea sobreescrita.
    """
    raise AuthenticatorNotRegisteredError(port="BearerAuthenticator", factory="get_bearer_authenticator")


async def get_api_key_authenticator() -> ApiKeyAuthenticator:
    """Retorna el autenticador de API keys registrado por `main.py`.

    `common` no posee implementación: `main.py` sobreescribe esta dependencia con la provista por
    `api-key`. Mientras no se registre, cualquier ruta a nivel de tenant fallará.

    Raises:
        AuthenticatorNotRegisteredError: Siempre, a menos que la dependencia sea sobreescrita.
    """
    raise AuthenticatorNotRegisteredError(port="ApiKeyAuthenticator", factory="get_api_key_authenticator")


async def get_tenant_session_revoker() -> TenantSessionRevoker:
    """Retorna el revocador de sesiones registrado por `main.py`.

    `common` no posee implementación: `main.py` sobreescribe esta dependencia con la provista por
    `iam`. Mientras no se registre, desactivar un tenant falla en vez de dejar a su gente con las
    sesiones vivas (SPEC-iam §3.1).

    Raises:
        SessionRevokerNotRegisteredError: Siempre, a menos que la dependencia sea sobreescrita.
    """
    raise SessionRevokerNotRegisteredError(port="TenantSessionRevoker", factory="get_tenant_session_revoker")


TenantSessionRevokerDep = Annotated[TenantSessionRevoker, Depends(get_tenant_session_revoker)]
"""Revocador de sesiones de un tenant, para el cambio de estado de `tenant` (SPEC-tenant §4)."""


_BearerTokenDep = Annotated[str | None, Depends(_bearer_scheme)]
"""Token extraído de `Authorization: Bearer <token>`, o `None` si no existe.

`OAuth2PasswordBearer` con `auto_error=False` ya retorna `None` para cualquier otro esquema
(`Basic`, ...), cabecera ausente o vacía; se usa solo como esquema de seguridad para que Swagger
UI muestre el flujo `OAuth2` estándar (botón "Authorize" con usuario/contraseña) en vez del campo
de token crudo de `HTTPBearer`. El token en sí sigue siendo el JWT que emite `POST /api/v1/auth/login`
(`iam`), sin cambios en `BearerAuthenticator.authenticate`.
"""
_ApiKeyDep = Annotated[str | None, Depends(_api_key_scheme)]
_BearerAuthenticatorDep = Annotated[BearerAuthenticator, Depends(get_bearer_authenticator)]
_ApiKeyAuthenticatorDep = Annotated[ApiKeyAuthenticator, Depends(get_api_key_authenticator)]


async def get_current_user(token: _BearerTokenDep, bearer: _BearerAuthenticatorDep) -> CurrentUser:
    """Autentica una ruta a nivel de usuario: solo JWT (SPEC-iam §3.4.1).

    Las cabeceras `X-API-Key` no se leen aquí, asegurando que credenciales de máquina
    no alcancen endpoints de gestión de usuarios o emisión de credenciales.

    Raises:
        UnauthorizedException: Si no se proporciona token Bearer o el autenticador lo rechaza.
    """
    if token is None:
        raise UnauthorizedException("Falta el access token Bearer.")
    return await bearer.authenticate(token)


async def get_auth_context(
    token: _BearerTokenDep,
    raw_key: _ApiKeyDep,
    bearer: _BearerAuthenticatorDep,
    api_keys: _ApiKeyAuthenticatorDep,
) -> AuthContext:
    """Autentica una ruta a nivel de tenant desde JWT o `X-API-Key`, nunca ambos (SPEC-iam §3.4.2).

    Raises:
        BadRequestException: Si ambas credenciales están presentes. Ninguna es verificada.
        UnauthorizedException: Si no existe credencial o el autenticador la rechaza.
        ForbiddenException: Si el JWT pertenece a un `SUPER_ADMIN`.
    """
    if token is not None and raw_key is not None:
        raise BadRequestException("Use JWT o X-API-Key, no ambas credenciales.")
    if raw_key is not None:
        return await api_keys.authenticate(raw_key)
    if token is None:
        raise UnauthorizedException("Falta JWT o X-API-Key.")
    user = await bearer.authenticate(token)
    if user.role is UserRole.SUPER_ADMIN:
        raise ForbiddenException("Un superadministrador no consume el API de tenant.")
    return AuthContext(tenant_id=user.tenant_id, user_id=user.user_id)


async def get_api_key_context(
    request: Request,
    raw_key: _ApiKeyDep,
    api_keys: _ApiKeyAuthenticatorDep,
) -> AuthContext:
    """Autentica rutas exclusivas de API key sin anunciar OAuth2 en OpenAPI."""
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    has_bearer = scheme.lower() == "bearer" and bool(token)
    if has_bearer and raw_key is not None:
        raise BadRequestException("Use JWT o X-API-Key, no ambas credenciales.")
    if has_bearer:
        raise ForbiddenException("Este endpoint solo acepta X-API-Key.")
    if raw_key is None:
        raise UnauthorizedException("Falta X-API-Key.")
    return await api_keys.authenticate(raw_key)


ApiKeyAuthContextDep = Annotated[AuthContext, Depends(get_api_key_context)]


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
"""Persona autenticada por JWT, para rutas a nivel de persona."""

AuthContextDep = Annotated[AuthContext, Depends(get_auth_context)]
"""Identidad de tenant desde un JWT o un API key, para rutas a nivel de tenant."""


def _ensure_rank(user: CurrentUser, minimum: UserRole) -> None:
    """Lanza `ForbiddenException` si el rango de `user` es inferior a `minimum`."""
    if _ROLE_RANK[user.role] < _ROLE_RANK[minimum]:
        raise ForbiddenException(f"La operación requiere el rol `{minimum}` o superior.")


def require_at_least(minimum: UserRole) -> Callable[..., Awaitable[CurrentUser]]:
    """Construye una dependencia que admite el rol `minimum` y cualquier rol superior (SPEC-iam §4).

    Example:
        >>> router = APIRouter(dependencies=[Depends(require_at_least(UserRole.TENANT_ADMIN))])

    Args:
        minimum: Rol más bajo admitido.

    Returns:
        Una dependencia que retorna el `CurrentUser` o genera `ForbiddenException` (403).
    """

    async def require_role(user: CurrentUserDep) -> CurrentUser:
        _ensure_rank(user, minimum)
        return user

    return require_role


def require_tenant_role(minimum: UserRole = UserRole.TENANT_MEMBER) -> Callable[..., Awaitable[CurrentUser]]:
    """Construye una dependencia para las rutas de persona `/my-*`: rol de tenant, al menos `minimum`.

    Representa la excepción deliberada a la jerarquía (SPEC-iam §4). Un `SUPER_ADMIN` tiene un
    tenant (`extech`), por lo que bajo `require_at_least` pasaría y vería datos de Extech
    en vez de los del cliente. Aquí recibe un 403 indicándole usar las rutas de administración.

    Args:
        minimum: Rol de tenant más bajo admitido: `TENANT_MEMBER` (por defecto) o `TENANT_ADMIN`.

    Returns:
        Una dependencia que retorna `CurrentUser` o genera `ForbiddenException` (403).

    Raises:
        ValueError: Si `minimum` no es un rol de tenant. Se lanza al declarar la ruta.
    """
    if minimum not in _TENANT_ROLES:
        raise ValueError(f"`minimum` must be a tenant role, got {minimum!r}.")

    async def require_own_tenant_role(user: CurrentUserDep) -> CurrentUser:
        if user.role not in _TENANT_ROLES:
            raise ForbiddenException(
                "Las rutas /my-* operan sobre el tenant propio; un superadministrador usa las rutas de administración."
            )
        _ensure_rank(user, minimum)
        return user

    return require_own_tenant_role
