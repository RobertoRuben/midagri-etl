"""Alcance de tenant compartido por todos los repositorios y las dependencias que lo construyen."""

from app.modules.common.tenancy.dependencies import (
    PlatformScopeDep,
    TenantScopeDep,
    platform_scope,
    provide_platform_scope,
    provide_tenant_scope,
)
from app.modules.common.tenancy.tenant_scope import TenantScope

__all__: list[str] = [
    "PlatformScopeDep",
    "TenantScope",
    "TenantScopeDep",
    "platform_scope",
    "provide_platform_scope",
    "provide_tenant_scope",
]
