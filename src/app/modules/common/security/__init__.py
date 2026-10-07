"""Contrato de autenticación compartido por todos los módulos: identidades, puertos y dependencias."""

from app.modules.common.security.auth_context import AuthContext
from app.modules.common.security.authenticators import (
    ApiKeyAuthenticator,
    AuthenticatorNotRegisteredError,
    BearerAuthenticator,
)
from app.modules.common.security.current_user import CurrentUser
from app.modules.common.security.dependencies import (
    API_KEY_HEADER,
    AuthContextDep,
    CurrentUserDep,
    TenantSessionRevokerDep,
    get_api_key_authenticator,
    get_auth_context,
    get_bearer_authenticator,
    get_current_user,
    get_tenant_session_revoker,
    require_at_least,
    require_tenant_role,
)
from app.modules.common.security.session_revoker import SessionRevokerNotRegisteredError, TenantSessionRevoker
from app.modules.common.security.user_role import UserRole

__all__: list[str] = [
    "API_KEY_HEADER",
    "ApiKeyAuthenticator",
    "AuthContext",
    "AuthContextDep",
    "AuthenticatorNotRegisteredError",
    "BearerAuthenticator",
    "CurrentUser",
    "CurrentUserDep",
    "SessionRevokerNotRegisteredError",
    "TenantSessionRevoker",
    "TenantSessionRevokerDep",
    "UserRole",
    "get_api_key_authenticator",
    "get_auth_context",
    "get_bearer_authenticator",
    "get_current_user",
    "get_tenant_session_revoker",
    "require_at_least",
    "require_tenant_role",
]
