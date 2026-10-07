"""Dependencia FastAPI del repositorio de subidas de la hoja `Registro` (PostgreSQL)."""

from typing import Annotated

from fastapi import Depends

from app.modules.common.db.dependencies import PgSessionDep
from app.modules.midagri.repository.impl.catalog_load_repository_impl import CatalogLoadRepositoryImpl
from app.modules.midagri.repository.interface.catalog_load_repository import CatalogLoadRepository


def get_catalog_load_repository(session: PgSessionDep) -> CatalogLoadRepository:
    """Subidas del Excel de registro."""
    return CatalogLoadRepositoryImpl(session)


CatalogLoadRepositoryDep = Annotated[CatalogLoadRepository, Depends(get_catalog_load_repository)]
