"""Dependencias FastAPI de los repositorios del catálogo, la multi gestión y el ubigeo (SQL Server)."""

from typing import Annotated

from fastapi import Depends

from app.modules.common.db.dependencies import MssqlSessionDep
from app.modules.midagri.repository.impl.catalog_repository_impl import CatalogRepositoryImpl
from app.modules.midagri.repository.impl.crop_repository_impl import CropRepositoryImpl
from app.modules.midagri.repository.impl.ubigeo_repository_impl import UbigeoRepositoryImpl
from app.modules.midagri.repository.interface.catalog_repository import CatalogRepository
from app.modules.midagri.repository.interface.crop_repository import CropRepository
from app.modules.midagri.repository.interface.ubigeo_repository import UbigeoRepository


def get_catalog_repository(session: MssqlSessionDep) -> CatalogRepository:
    """Repositorio del catálogo de productos de mercado."""
    return CatalogRepositoryImpl(session)


def get_crop_repository(session: MssqlSessionDep) -> CropRepository:
    """Repositorio de cultivos de la multi gestión."""
    return CropRepositoryImpl(session)


def get_ubigeo_repository(session: MssqlSessionDep) -> UbigeoRepository:
    """Repositorio de ubigeos."""
    return UbigeoRepositoryImpl(session)


CatalogRepositoryDep = Annotated[CatalogRepository, Depends(get_catalog_repository)]
CropRepositoryDep = Annotated[CropRepository, Depends(get_crop_repository)]
UbigeoRepositoryDep = Annotated[UbigeoRepository, Depends(get_ubigeo_repository)]
