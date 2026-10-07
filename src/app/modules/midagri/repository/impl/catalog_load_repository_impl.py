"""Subidas de la hoja `Registro` en PostgreSQL."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.repository.impl.generic_repository_impl import GenericRepositoryImpl
from app.modules.midagri.model.pg import CatalogLoad, CatalogLoadItem
from app.modules.midagri.repository.interface.catalog_load_repository import CatalogLoadRepository


class CatalogLoadRepositoryImpl(GenericRepositoryImpl[CatalogLoad], CatalogLoadRepository):
    """`catalog_load` y sus filas."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CatalogLoad, session)

    async def list_recent(self, page: int, size: int) -> tuple[list[CatalogLoad], int]:
        total = await self.count()
        stmt = select(CatalogLoad).order_by(CatalogLoad.id.desc()).offset((page - 1) * size).limit(size)
        return list(await self.session.scalars(stmt)), total

    async def add_item(self, item: CatalogLoadItem) -> None:
        self.session.add(item)
        await self.session.flush()

    async def list_items(self, catalog_load_id: int) -> list[CatalogLoadItem]:
        stmt = (
            select(CatalogLoadItem)
            .where(CatalogLoadItem.catalog_load_id == catalog_load_id)
            .order_by(CatalogLoadItem.row_number, CatalogLoadItem.id)
        )
        return list(await self.session.scalars(stmt))
