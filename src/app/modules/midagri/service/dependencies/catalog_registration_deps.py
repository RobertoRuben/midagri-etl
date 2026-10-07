"""Dependencia FastAPI del registro de faltantes desde la hoja `Registro` (D33)."""

from typing import Annotated

from fastapi import Depends

from app.modules.common.db.dependencies import MssqlSessionDep, PgSessionDep
from app.modules.midagri.repository.dependencies.catalog_load_repository_deps import CatalogLoadRepositoryDep
from app.modules.midagri.repository.dependencies.catalog_registry_deps import CatalogRepositoryDep, CropRepositoryDep
from app.modules.midagri.service.impl.catalog_registration_service_impl import CatalogRegistrationServiceImpl
from app.modules.midagri.service.interface.catalog_registration_service import CatalogRegistrationService


def get_catalog_registration_service(
    catalog: CatalogRepositoryDep,
    crops: CropRepositoryDep,
    loads: CatalogLoadRepositoryDep,
    mssql: MssqlSessionDep,
    pg: PgSessionDep,
) -> CatalogRegistrationService:
    """Registro de productos con el SP del app. FastAPI reutiliza las sesiones dentro de la solicitud."""
    return CatalogRegistrationServiceImpl(catalog, crops, loads, mssql=mssql, pg=pg)


CatalogRegistrationServiceDep = Annotated[CatalogRegistrationService, Depends(get_catalog_registration_service)]
