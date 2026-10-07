"""Dependencia FastAPI del reporte de faltantes."""

from typing import Annotated

from fastapi import Depends

from app.modules.midagri.repository.dependencies.catalog_registry_deps import CatalogRepositoryDep, CropRepositoryDep
from app.modules.midagri.repository.dependencies.sisap_repository_dep import SisapRepositoryDep
from app.modules.midagri.service.impl.gap_service_impl import GapServiceImpl
from app.modules.midagri.service.interface.gap_service import GapService


def get_gap_service(sisap: SisapRepositoryDep, crops: CropRepositoryDep, catalog: CatalogRepositoryDep) -> GapService:
    """Reporte de faltantes (portal SISAP + SQL Server)."""
    return GapServiceImpl(sisap, crops, catalog)


GapServiceDep = Annotated[GapService, Depends(get_gap_service)]
