"""Dependencia FastAPI de la carga de precios."""

from typing import Annotated

from fastapi import Depends

from app.modules.midagri.repository.dependencies.catalog_registry_deps import (
    CatalogRepositoryDep,
    CropRepositoryDep,
    UbigeoRepositoryDep,
)
from app.modules.midagri.repository.dependencies.price_repository_deps import PriceRepositoryDep
from app.modules.midagri.repository.dependencies.sisap_repository_dep import SisapRepositoryDep
from app.modules.midagri.service.impl.ingestion_service_impl import IngestionServiceImpl
from app.modules.midagri.service.interface.ingestion_service import IngestionService


def get_ingestion_service(
    sisap: SisapRepositoryDep,
    crops: CropRepositoryDep,
    catalog: CatalogRepositoryDep,
    ubigeo: UbigeoRepositoryDep,
    prices: PriceRepositoryDep,
) -> IngestionService:
    """Carga de precios de un mercado (portal SISAP + SQL Server)."""
    return IngestionServiceImpl(sisap, crops, catalog, ubigeo, prices)


IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]
