"""Decorador `@query`: consulta SQL nativa validada contra la anotación de retorno del método.

El cuerpo del método decorado no se ejecuta: `@query` corre el SQL con los `kwargs` como parámetros
ligados y valida el resultado con Pydantic. Sirve para las lecturas que un ORM resolvería con una
consulta por fila —el N+1 que SPEC-catalog §4 prohíbe en el camino de ejecución— y que en SQL son
una sola sentencia.

**Columnas JSON.** Una agregación de Postgres (`json_agg`, `json_build_object`, `jsonb_agg`) evita
la segunda consulta para las colecciones anidadas, pero asyncpg entrega `json` y `jsonb` como
`str`: sin desarmarlos, validar `list[LabelDTO]` contra una cadena falla. `@query` mira el DTO de
retorno, marca los campos cuyo valor es compuesto —`list`, `dict`, `tuple`, `set` o un `BaseModel`
anidado— y les aplica `json.loads` **solo si llegan como cadena**. Un campo `str` nunca se toca, y
un driver que ya devuelva objetos (psycopg con su códec, o un doble en tests) pasa sin cambios.
"""

import json
from collections.abc import Callable
from functools import wraps
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.exception import NotFoundException

_SCALAR_TYPES = (int, str, float, bool, bytes)
# Orígenes cuya representación natural en Postgres es una columna `json`/`jsonb`. `bytes` no está:
# es escalar y llega como `bytea`, no como cadena JSON.
_STRUCTURED_ORIGINS = (list, dict, tuple, set, frozenset)


def query(sql: str) -> Callable[[Callable], Callable]:
    """Ejecuta `sql` en lugar del cuerpo del método y valida el resultado contra su tipo de retorno.

    El modo sale de la anotación de retorno: `None` no devuelve nada, un escalar usa
    `scalar_one_or_none`, `list[int]` (o de otro escalar) devuelve la primera columna de cada fila,
    `list[T]` valida todas las filas contra el DTO `T`, `T | None` valida la primera o devuelve
    `None`, y `T` a secas exige que haya fila.

    Args:
        sql: Sentencia con parámetros con nombre (`:tenant_id`). Los valores salen de los `kwargs`
            de la llamada, así que **los argumentos posicionales se descartan**: los métodos
            decorados declaran sus parámetros como keyword-only.

    Returns:
        El decorador que reemplaza el cuerpo del método.
    """

    def decorator(f: Callable) -> Callable:
        return_type = get_type_hints(f).get("return")
        mode, adapter, json_columns = _resolve(return_type)
        func_name = getattr(f, "__name__", repr(f))

        @wraps(f)
        async def wrapper(self, *args, **kwargs):
            session: AsyncSession = self.session
            result = await session.execute(text(sql), kwargs)

            if mode == "none":
                return None
            if mode == "scalar":
                return result.scalar_one_or_none()
            if mode == "scalar_list":
                return list(result.scalars().all())
            if mode == "list":
                assert adapter is not None
                rows = [_decode(row, json_columns, func_name) for row in result.mappings().all()]
                return adapter.validate_python(rows)

            row = result.mappings().first()
            if row is None:
                if mode == "single_required":
                    raise NotFoundException(f"No row returned by '{func_name}'")
                return None
            assert adapter is not None
            return adapter.validate_python(_decode(row, json_columns, func_name))

        return wrapper

    return decorator


def _resolve(return_type) -> tuple[str, TypeAdapter | None, frozenset[str]]:
    """Deriva de la anotación de retorno el modo, el validador y las columnas JSON del DTO."""
    if return_type is None or return_type is type(None):
        return "none", None, frozenset()

    origin = get_origin(return_type)

    if origin is list:
        inner = get_args(return_type)[0]
        if inner in _SCALAR_TYPES:
            # `list[int]` y compañía: una columna por fila, sin DTO. `scalars()` ya devuelve la lista;
            # validar `{"inference_model_id": 5}` contra `int` fallaría.
            return "scalar_list", None, frozenset()
        return "list", TypeAdapter(list[inner]), _json_columns(inner)

    if origin in (Union, UnionType):
        non_none = [a for a in get_args(return_type) if a is not type(None)]
        if len(non_none) == 1:
            # `int | None` y compañía son escalares opcionales: `scalar_one_or_none`
            # ya devuelve `None` cuando no hubo filas. Sin este caso caerían en
            # `single_optional`, que intentaría validar la fila `{"id": 5}`
            # contra `int` y fallaría.
            if non_none[0] in _SCALAR_TYPES:
                return "scalar", None, frozenset()
            return "single_optional", TypeAdapter(non_none[0]), _json_columns(non_none[0])

    if return_type in _SCALAR_TYPES:
        return "scalar", None, frozenset()

    return "single_required", TypeAdapter(return_type), _json_columns(return_type)


def _is_structured(annotation: Any) -> bool:
    """Indica si la anotación describe un valor compuesto, o sea el que viaja como `json` desde Postgres.

    Un opcional se mira por dentro: `list[LabelDTO] | None` es compuesto igual, porque la columna
    puede ser `NULL` sin dejar de ser JSON cuando trae valor.
    """
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return any(_is_structured(arg) for arg in get_args(annotation) if arg is not type(None))
    if origin in _STRUCTURED_ORIGINS:
        return True
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _json_columns(model: Any) -> frozenset[str]:
    """Nombres de columna del DTO cuyo valor se espera como JSON.

    Se incluyen el nombre del campo y sus alias, porque la clave que llega es la etiqueta de la
    columna en el `SELECT` y el DTO puede recibirla por alias de validación.
    """
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        return frozenset()

    names: set[str] = set()
    for name, field in model.model_fields.items():
        if not _is_structured(field.annotation):
            continue
        names.add(name)
        if field.alias is not None:
            names.add(field.alias)
        if isinstance(field.validation_alias, str):
            names.add(field.validation_alias)
    return frozenset(names)


def _decode(row: RowMapping, json_columns: frozenset[str], func_name: str) -> dict[str, Any]:
    """Desarma las columnas JSON de una fila, dejando el resto intacto.

    Raises:
        ValueError: Si una columna marcada como JSON trae una cadena que no lo es. Se prefiere a
            dejar que Pydantic falle después: el mensaje nombra la columna y la consulta.
    """
    if not json_columns:
        return dict(row)

    decoded: dict[str, Any] = {}
    for key, value in row.items():
        if key in json_columns and isinstance(value, str):
            try:
                decoded[key] = json.loads(value)
            except json.JSONDecodeError as error:
                raise ValueError(f"La columna '{key}' de '{func_name}' no trae JSON válido: {error}") from error
        else:
            decoded[key] = value
    return decoded
