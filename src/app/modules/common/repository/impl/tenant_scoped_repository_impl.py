"""Implementación de repositorio genérico acotado por tenant (SPEC-tenant §3.2)."""

from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute

from app.modules.common.model.base_model import Base
from app.modules.common.repository.impl.generic_repository_impl import GenericRepositoryImpl
from app.modules.common.tenancy.tenant_scope import TenantScope


class TenantScopedRepositoryImpl[T: Base](GenericRepositoryImpl[T]):
    """Repositorio genérico que acota todas sus lecturas y escrituras al tenant del alcance.

    Los repositorios de tablas con columna `tenant_id` heredan de esta clase en lugar de
    `GenericRepositoryImpl`, garantizando que el aislamiento multitenant sea el comportamiento
    por defecto y que omitirlo requiera un esfuerzo deliberado.

    Attributes:
        _tenant_column: Nombre de la columna de tenant en el modelo (por defecto 'tenant_id').
        _scope: Alcance de tenant (`TenantScope`) inyectado para la unidad de trabajo.
    """

    _tenant_column: ClassVar[str] = "tenant_id"

    def __init__(self, model: type[T], session: AsyncSession, scope: TenantScope) -> None:
        """Inicializa el repositorio acotado por tenant.

        Args:
            model: Clase del modelo SQLAlchemy que hereda de `Base`.
            session: Sesión asíncrona de SQLAlchemy.
            scope: Alcance de tenant asociado a la solicitud o proceso.
        """
        super().__init__(model, session)
        self._scope = scope

    def _get_tenant_attr(self) -> InstrumentedAttribute[int]:
        """Retorna el atributo o columna del modelo que representa el identificador del tenant.

        Returns:
            InstrumentedAttribute correspondiente a la columna de tenant.

        Raises:
            AttributeError: Si el modelo no cuenta con la columna configurada en `_tenant_column`.
        """
        return getattr(self._model, self._tenant_column)

    async def save(self, entity: T) -> T:
        """Guarda una entidad estampando o validando el `tenant_id` del alcance.

        Si la entidad no tiene `tenant_id`, se le asigna el del alcance actual.
        Si ya posee uno distinto, se rechaza la operación para prevenir escrituras cruzadas.

        Args:
            entity: Instancia del modelo a persistir.

        Returns:
            La entidad persistida tras `flush` y `refresh`.

        Raises:
            ValueError: Si el alcance de plataforma no recibe `tenant_id` explícito en la entidad,
                o si la entidad declara un `tenant_id` que difiere del alcance activo.
        """
        current = getattr(entity, self._tenant_column, None)
        if self._scope.cross_tenant:
            if current is None:
                raise ValueError("Un alcance de plataforma exige tenant_id explícito en la entidad.")
        elif current is None:
            setattr(entity, self._tenant_column, self._scope.tenant_id)
        elif current != self._scope.tenant_id:
            raise ValueError(f"La entidad declara tenant_id={current} y el alcance es {self._scope.tenant_id}.")
        return await super().save(entity)

    async def bulk_save(self, entities: list[T]) -> list[T]:
        """Persiste múltiples entidades estampando o validando el `tenant_id` del alcance.

        Args:
            entities: Lista de entidades del modelo a persistir.

        Returns:
            Lista de entidades persistidas.

        Raises:
            ValueError: Si alguna entidad infringe las validaciones del alcance de tenant.
        """
        for entity in entities:
            current = getattr(entity, self._tenant_column, None)
            if self._scope.cross_tenant:
                if current is None:
                    raise ValueError("Un alcance de plataforma exige tenant_id explícito en la entidad.")
            elif current is None:
                setattr(entity, self._tenant_column, self._scope.tenant_id)
            elif current != self._scope.tenant_id:
                raise ValueError(f"La entidad declara tenant_id={current} y el alcance es {self._scope.tenant_id}.")
        return await super().bulk_save(entities)

    async def get_all(self) -> list[T]:
        """Obtiene todas las entidades acotadas al tenant del alcance.

        Returns:
            Lista de entidades correspondientes al tenant activo.
        """
        stmt = self._scope.apply(select(self._model), self._get_tenant_attr())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Cuenta la cantidad total de entidades acotadas al tenant del alcance.

        Returns:
            Número total de registros encontrados para el tenant.
        """
        stmt = self._scope.apply(
            select(func.count()).select_from(self._model),
            self._get_tenant_attr(),
        )
        total = await self.session.scalar(stmt)
        return total or 0

    async def get_by_id(self, id: int) -> T | None:
        """Obtiene una entidad por su clave primaria respetando el alcance del tenant.

        Implementado deliberadamente mediante `select()` explícito en lugar de `session.get()`
        para evitar resolver entidades de otros tenants almacenadas en el identity map.

        Args:
            id: Identificador único del registro.

        Returns:
            La entidad coincidente o None si no existe o pertenece a otro tenant.
        """
        stmt = self._scope.apply(
            select(self._model).where(self._model.id == id),
            self._get_tenant_attr(),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by(self, attr: InstrumentedAttribute, value: Any) -> T | None:
        """Obtiene una entidad por un atributo específico acotada al tenant del alcance.

        Args:
            attr: Columna o atributo del modelo a filtrar.
            value: Valor buscado.

        Returns:
            La primera entidad coincidente o None.
        """
        stmt = self._scope.apply(
            select(self._model).where(attr == value),
            self._get_tenant_attr(),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_all_by(self, attr: InstrumentedAttribute, value: Any) -> list[T]:
        """Obtiene todas las entidades que coincidan con un atributo dentro del alcance del tenant.

        Args:
            attr: Columna o atributo del modelo a filtrar.
            value: Valor buscado.

        Returns:
            Lista de entidades coincidentes.
        """
        stmt = self._scope.apply(
            select(self._model).where(attr == value),
            self._get_tenant_attr(),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def exist_by(self, attr: InstrumentedAttribute, value: Any) -> bool:
        """Determina si existe al menos una entidad con el valor dado acotada al tenant.

        Args:
            attr: Columna o atributo a evaluar.
            value: Valor buscado.

        Returns:
            True si existe coincidencia en el tenant del alcance; False en caso contrario.
        """
        base_stmt = select(1).select_from(self._model).where(attr == value)
        stmt = select(self._scope.apply(base_stmt, self._get_tenant_attr()).exists())
        return bool(await self.session.scalar(stmt))

    async def delete_by_id(self, id: int) -> None:
        """Elimina una entidad por su ID únicamente si pertenece al tenant del alcance.

        Args:
            id: Identificador de la entidad a eliminar.
        """
        entity = await self.get_by_id(id)
        if entity is not None:
            await self.session.delete(entity)
            await self.session.flush()

    async def bulk_delete(self, ids: list[int]) -> None:
        """Elimina en lote entidades por ID acotando la sentencia al tenant del alcance.

        Añade `WHERE tenant_id = :tenant_id` sobre la consulta `Delete` para evitar que un
        alcance de tenant borre registros de otro.

        Args:
            ids: Lista de identificadores únicos a eliminar.
        """
        stmt = delete(self._model).where(self._model.id.in_(ids))
        if not self._scope.cross_tenant:
            stmt = stmt.where(self._get_tenant_attr() == self._scope.tenant_id)
        await self.session.execute(stmt)
        await self.session.flush()

    async def paginate(self, page: int, size: int) -> tuple[list[T], int]:
        """Obtiene una página de resultados y el conteo total acotados al tenant del alcance.

        Args:
            page: Número de página solicitada (iniciando en 1).
            size: Cantidad máxima de registros por página.

        Returns:
            Tupla conteniendo la lista de registros de la página y el total global del tenant.
        """
        total = await self.count()
        stmt = self._scope.apply(
            select(self._model).order_by(self._model.id).offset((page - 1) * size).limit(size),
            self._get_tenant_attr(),
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total
