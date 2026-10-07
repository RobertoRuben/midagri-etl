"""Decorador para delimitar transacciones en métodos de servicios asíncronos."""

from collections.abc import Callable
from functools import wraps
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

TRANSACTIONAL_MANAGED_KEY: Final[str] = "_transactional_managed"


def _resolve_session(obj: Any, path: str) -> AsyncSession:
    """Resuelve la sesión SQLAlchemy a partir de la ruta de atributos configurada en la clase."""
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def transactional(func: Callable | None = None, *, read_only: bool = False):
    """Decorador para ejecutar un método dentro de una unidad de trabajo transaccional.

    Si la sesión no tiene transacción activa, inicia una con `session.begin()`.
    Si ya existe una transacción iniciada por otro `@transactional`, participa en ella.
    Si existe una transacción abierta por autobegin (p. ej. una lectura previa en la misma sesión),
    adopta dicha transacción: ejecuta el método, realiza `commit()` al finalizar y `rollback()`
    en caso de excepción (SPEC-tenant §3.5).

    Args:
        func: Función o método asíncrono a decorar.
        read_only: Si es True, no gestiona transacciones y ejecuta la función directamente.

    Returns:
        Función decorada.

    Raises:
        AttributeError: Si la clase no define `__session_attr__`.
    """

    def decorator(f: Callable):
        @wraps(f)
        async def wrapper(self, *args, **kwargs):
            path: str | None = getattr(type(self), "__session_attr__", None)
            if path is None:
                raise AttributeError(
                    f"{type(self).__name__} debe declarar "
                    f"`__session_attr__` para usar @transactional "
                    f"(p. ej. `__session_attr__ = 'plan_repository.session'`)."
                )
            session: AsyncSession = _resolve_session(self, path)

            if read_only:
                return await f(self, *args, **kwargs)

            # Caso 1: La transacción ya está siendo gestionada por un @transactional externo
            if session.in_transaction() and session.info.get(TRANSACTIONAL_MANAGED_KEY):
                return await f(self, *args, **kwargs)

            # Caso 2: Transacción activa pero sin la marca (autobegin de una consulta previa).
            # Se adopta la transacción: ejecuta, confirma y revierte en caso de error.
            if session.in_transaction():
                session.info[TRANSACTIONAL_MANAGED_KEY] = True
                try:
                    result = await f(self, *args, **kwargs)
                    await session.commit()
                    return result
                except Exception:
                    await session.rollback()
                    raise
                finally:
                    session.info.pop(TRANSACTIONAL_MANAGED_KEY, None)

            # Caso 3: No hay transacción activa; se inicia una nueva unidad de trabajo.
            session.info[TRANSACTIONAL_MANAGED_KEY] = True
            try:
                async with session.begin():
                    return await f(self, *args, **kwargs)
            finally:
                session.info.pop(TRANSACTIONAL_MANAGED_KEY, None)

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
