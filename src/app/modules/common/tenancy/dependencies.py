"""Dependencias que convierten la identidad autenticada en un `TenantScope` (SPEC-tenant §3.6).

Este es el único archivo autorizado para construir el alcance de plataforma (`cross_tenant=True`).
Las pruebas automatizadas verifican que ningún otro archivo lo construya directamente.
"""

from typing import Annotated

from fastapi import Depends

from app.modules.common.exception import ForbiddenException
from app.modules.common.security import AuthContextDep, CurrentUserDep, UserRole
from app.modules.common.tenancy.tenant_scope import TenantScope


async def provide_tenant_scope(auth: AuthContextDep) -> TenantScope:
    """Retorna el alcance del tenant para el cual se autenticó la solicitud (JWT o API key)."""
    return TenantScope(tenant_id=auth.tenant_id)


async def provide_platform_scope(user: CurrentUserDep) -> TenantScope:
    """Retorna el alcance de plataforma, el cual no filtra registros, reservado para `SUPER_ADMIN`.

    Raises:
        UnauthorizedException: Si no se proporciona un token Bearer válido.
        ForbiddenException: Si el usuario no tiene el rol `SUPER_ADMIN`.
    """
    if user.role is not UserRole.SUPER_ADMIN:
        raise ForbiddenException(f"La operación requiere el rol `{UserRole.SUPER_ADMIN}`.")
    return platform_scope()


def platform_scope() -> TenantScope:
    """Construye el alcance interno de plataforma desde el único archivo autorizado."""
    return TenantScope(cross_tenant=True)


TenantScopeDep = Annotated[TenantScope, Depends(provide_tenant_scope)]
"""Alcance del tenant autenticado, para rutas de nivel de tenant."""

PlatformScopeDep = Annotated[TenantScope, Depends(provide_platform_scope)]
"""Alcance cross-tenant de plataforma, para rutas de administración. Requiere `SUPER_ADMIN`."""
