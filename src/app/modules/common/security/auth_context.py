"""Identidad de tenant de una solicitud, independientemente de la credencial usada (SPEC-iam §3, §3.4)."""

from pydantic import BaseModel, ConfigDict


class AuthContext(BaseModel):
    """Identidad de tenant en una solicitud, proveniente de un JWT de tenant o un `X-API-Key`. Inmutable.

    Los servicios lo reciben sin necesidad de saber qué credencial fue utilizada (SPEC-iam §3.4.2);
    `app.modules.common.tenancy.provide_tenant_scope` lo convierte en el `TenantScope` de la solicitud.

    Attributes:
        tenant_id: Identificador del tenant en cuyo nombre actúa la solicitud.
        user_id: Presente cuando la credencial utilizada fue un JWT de tenant.
        api_key_id: Presente cuando la credencial fue un API key, permitiendo atribuir el consumo.
    """

    model_config = ConfigDict(frozen=True)

    tenant_id: int
    user_id: int | None = None
    api_key_id: int | None = None
