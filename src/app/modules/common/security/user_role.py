"""Roles de una persona autenticada (SPEC-iam §2)."""

from enum import StrEnum


class UserRole(StrEnum):
    """Rol de una persona autenticada.

    Los valores representan la forma pública en minúsculas utilizada en los claims de tokens y OpenAPI.
    La base de datos almacena el nombre del miembro (`SUPER_ADMIN`), tal como SQLAlchemy hace para cualquier `Enum`.
    La jerarquía entre roles se define en `app.modules.common.security.dependencies`.
    """

    SUPER_ADMIN = "super_admin"
    TENANT_ADMIN = "tenant_admin"
    TENANT_MEMBER = "tenant_member"
