"""Alcance de tenant de una unidad de trabajo (SPEC-tenant §3.1)."""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import Select
from sqlalchemy.orm import InstrumentedAttribute


class TenantScope(BaseModel):
    """Alcance de tenant de una unidad de trabajo. Inmutable.

    Es un alcance acotado a un tenant (`tenant_id` establecido) o un alcance de plataforma (`cross_tenant`
    activo), nunca ambos y nunca ninguno. Únicamente
    `app.modules.common.tenancy.dependencies.provide_platform_scope` construye el alcance de plataforma.

    Attributes:
        tenant_id: Tenant al que se restringe toda consulta. Obligatorio salvo cuando `cross_tenant` es True.
        cross_tenant: Alcance de plataforma, reservado para `SUPER_ADMIN`. No aplica filtros de tenant.
    """

    model_config = ConfigDict(frozen=True)

    tenant_id: int | None = None
    cross_tenant: bool = False

    @model_validator(mode="after")
    def _validate_exclusive(self) -> Self:
        """Rechaza un alcance de plataforma con tenant_id o un alcance sin ninguno de los dos."""
        if self.cross_tenant and self.tenant_id is not None:
            raise ValueError("Un alcance de plataforma no lleva tenant_id.")
        if not self.cross_tenant and self.tenant_id is None:
            raise ValueError("Un alcance de tenant exige tenant_id.")
        return self

    def apply[StmtT: Select[Any]](self, stmt: StmtT, column: InstrumentedAttribute[int]) -> StmtT:
        """Restringe `stmt` al tenant de este alcance.

        Args:
            stmt: Consulta a restringir. No se muta directamente (`Select` es generativo).
            column: Columna del tenant en el modelo consultado, p. ej. `User.tenant_id`.

        Returns:
            Una copia de `stmt` filtrada por `column == tenant_id`, o la misma `stmt` en alcance de plataforma.
        """
        return stmt if self.cross_tenant else stmt.where(column == self.tenant_id)
