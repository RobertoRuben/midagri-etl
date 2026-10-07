from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, delete, func, inspect, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm.attributes import InstrumentedAttribute

from app.modules.common.repository.interface.generic_repository import GenericRepository


class GenericRepositoryImpl[T: DeclarativeBase](GenericRepository[T]):
    """Repositorio CRUD genérico para cualquier modelo mapeado.

    Sirve para los modelos de PostgreSQL (`common.model.Base`, PK `id`) y para los de SQL Server
    (`MssqlBase`, con PK de nombre propio como `MultivalorId`): la PK se lee del mapeo, no se asume `id`.
    Sobre las tablas ajenas de SQL Server solo se usan las lecturas (fase 1).
    """

    def __init__(self, model: type[T], session: AsyncSession) -> None:
        self._model = model
        self.session = session

    @property
    def _pk(self) -> ColumnElement[Any]:
        """Columna de la clave primaria del modelo (se exige una PK simple)."""
        primary_key = inspect(self._model).primary_key
        if len(primary_key) != 1:
            raise TypeError(f"{self._model.__name__} tiene una PK compuesta; GenericRepositoryImpl exige una simple.")
        return primary_key[0]

    async def save(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def get_all(self) -> list[T]:
        result = await self.session.execute(select(self._model))
        return list(result.scalars().all())

    async def count(self) -> int:
        total = await self.session.scalar(select(func.count()).select_from(self._model))
        return total or 0

    async def get_by_id(self, id: Any) -> T | None:
        return await self.session.get(self._model, id)

    async def get_by(self, attr: InstrumentedAttribute, value: Any) -> T | None:
        stmt = select(self._model).where(attr == value)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_all_by(self, attr: InstrumentedAttribute, value: Any) -> list[T]:
        stmt = select(self._model).where(attr == value)
        return list((await self.session.execute(stmt)).scalars().all())

    async def exist_by(self, attr: InstrumentedAttribute, value: Any) -> bool:
        # `SELECT EXISTS (...)` no es válido en SQL Server; `LIMIT 1` / `TOP 1` sirve en ambas bases.
        stmt = select(literal(1)).select_from(self._model).where(attr == value).limit(1)
        return await self.session.scalar(stmt) is not None

    async def delete_by_id(self, id: Any) -> None:
        entity = await self.session.get(self._model, id)
        if entity:
            await self.session.delete(entity)
            await self.session.flush()

    async def bulk_save(self, entities: list[T]) -> list[T]:
        """add_all + UN solo flush. El flush puebla los PK autoincrement vía
        INSERT ... RETURNING (insertmanyvalues); NO se hace refresh por entidad
        (eso sería un N+1 de SELECTs). Si el caller necesita columnas con
        server_default (created_at/updated_at), debe re-consultar en batch."""
        self.session.add_all(entities)
        await self.session.flush()
        return entities

    async def bulk_delete(self, ids: list[Any]) -> None:
        await self.session.execute(delete(self._model).where(self._pk.in_(ids)))
        await self.session.flush()

    async def paginate(self, page: int, size: int) -> tuple[list[T], int]:
        total = await self.session.scalar(select(func.count()).select_from(self._model)) or 0
        stmt = select(self._model).order_by(self._pk).offset((page - 1) * size).limit(size)
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total
