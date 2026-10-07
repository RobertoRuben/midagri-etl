"""Contrato de las subidas de la hoja `Registro` (`catalog_load`, `catalog_load_item`, PostgreSQL)."""

from typing import Protocol

from app.modules.common.repository.interface.generic_repository import GenericRepository
from app.modules.midagri.model.pg import CatalogLoad, CatalogLoadItem


class CatalogLoadRepository(GenericRepository[CatalogLoad], Protocol):
    """Subidas del Excel a `POST /catalog/registrations`."""

    async def list_recent(self, page: int, size: int) -> tuple[list[CatalogLoad], int]:
        """Página de subidas, la más reciente primero, y el total."""
        ...

    async def add_item(self, item: CatalogLoadItem) -> None:
        """Agrega el resultado de una fila (sin confirmar: lo hace el service)."""
        ...

    async def list_items(self, catalog_load_id: int) -> list[CatalogLoadItem]:
        """Filas de una subida, en orden de fila."""
        ...
