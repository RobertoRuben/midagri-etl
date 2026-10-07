"""Traza de la excepción en curso para el log de una ejecución (D37)."""

import traceback

MAX_TRACE = 8000
"""Caracteres que se guardan de cada traza: los últimos, donde está la causa."""


def format_trace(limit: int = MAX_TRACE) -> str | None:
    """Traza de la excepción que se está manejando, recortada a sus últimos `limit` caracteres.

    Se llama dentro de un `except`. Fuera de uno devuelve `None`.
    """
    trace = traceback.format_exc()
    if trace.strip() == "NoneType: None":
        return None
    return trace if len(trace) <= limit else "…\n" + trace[-limit:]
