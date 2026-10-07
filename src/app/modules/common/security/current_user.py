"""Persona autenticada mediante un JWT (SPEC-iam §3)."""

from pydantic import BaseModel, ConfigDict

from app.modules.common.security.user_role import UserRole


class CurrentUser(BaseModel):
    """Persona autenticada por un access token. Inmutable.

    Se reconstruye a partir de los claims del token sin consultar la base de datos (SPEC-iam §3.1),
    por lo que puede diferir como máximo durante el tiempo de vida de un access token.

    Attributes:
        user_id: Identificador del usuario autenticado.
        role: Rol asignado cuando se emitió el token.
        tenant_id: Tenant al que pertenece el usuario. Siempre establecido: un `SUPER_ADMIN` pertenece a `extech`.
        session_id: Sesión de refresh que emitió este token (claim `sid`). Es lo que permite saber
            cuál es "la sesión actual" sin pedirle nada al cliente. `None` en un token emitido
            antes de que el claim existiera: vale durante su vida (30 min) y después desaparece.
    """

    model_config = ConfigDict(frozen=True)

    user_id: int
    role: UserRole
    tenant_id: int
    session_id: int | None = None
