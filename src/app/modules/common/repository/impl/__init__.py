"""Implementaciones de repositorios genéricos y acotados por tenant."""

from app.modules.common.repository.impl.generic_repository_impl import GenericRepositoryImpl
from app.modules.common.repository.impl.tenant_scoped_repository_impl import TenantScopedRepositoryImpl

__all__: list[str] = [
    "GenericRepositoryImpl",
    "TenantScopedRepositoryImpl",
]
