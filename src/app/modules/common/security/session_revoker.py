"""Puerto de revocación de sesiones, implementado fuera de `common` (SPEC-tenant §3.6).

Desactivar un tenant debe revocar las sesiones de refresh de todos sus usuarios, en la misma
transacción (`SPEC-tenant.md` §4, `SPEC-iam.md` §3.1 condición 3). Esas filas son de `iam`, y
`tenant` no puede importar `iam` (dirección de dependencias de `CAPABILITY-MAP.md`; además `iam`
ya depende de `tenant`, así que el import inverso cerraría un ciclo).

La salida es la misma que para la autenticación: `common` declara el `Protocol`, `iam` aporta la
implementación y `main.py` la registra. `tenant` solo conoce este archivo.
"""

from typing import Protocol


class TenantSessionRevoker(Protocol):
    """Revoca las sesiones de refresh de todos los usuarios de un tenant. Implementado por `iam`."""

    async def revoke_tenant_sessions(self, tenant_id: int) -> int:
        """Revoca todas las sesiones activas de los usuarios de `tenant_id`.

        Recibe un `tenant_id` y nada más: la implementación llega ya ligada a la sesión de la
        solicitud, igual que cualquier repositorio inyectado. Pasarle una `AsyncSession` volvería
        la sesión parte del contrato de `common` y permitiría invocarla con otra distinta de la
        que abrió la unidad de trabajo — justo lo que rompería la atomicidad que esto existe para
        garantizar.

        No confirma la transacción: quien la invoca ya está dentro de un `@transactional` y es
        quien decide cuándo cerrar la unidad de trabajo.

        Args:
            tenant_id: Tenant cuyas sesiones se revocan.

        Returns:
            Cantidad de sesiones que pasaron de activas a revocadas. Cero es un resultado válido:
            un tenant sin nadie conectado.
        """
        ...


class SessionRevokerNotRegisteredError(RuntimeError):
    """Error emitido cuando se ejecuta la dependencia del revocador sin implementación en `main.py`.

    Es un error de despliegue, no de cliente, así que deliberadamente no es
    `ProblemDetailsException`: el manejador genérico responde 500 sin detalles internos y registra
    el mensaje con su traza. La operación que lo provocó **no se aplica**: la dependencia falla al
    resolverse, antes del cuerpo del endpoint, de modo que no queda un tenant desactivado con las
    sesiones de su gente todavía vivas.

    Attributes:
        port: Protocolo que carece de implementación registrada.
        factory: Dependencia de fábrica que `main.py` debe registrar.
    """

    def __init__(self, port: str, factory: str) -> None:
        self.port = port
        self.factory = factory
        super().__init__(
            f"No {port} is registered: main.py must provide an implementation for `{factory}`. "
            "Refusing to change the tenant status."
        )
