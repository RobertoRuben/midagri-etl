"""Dependencias FastAPI de mercados y precios (SQL Server)."""

from typing import Annotated

from fastapi import Depends

from app.modules.common.db.dependencies import MssqlSessionDep
from app.modules.midagri.repository.impl.price_repository_impl import MarketRepositoryImpl, PriceRepositoryImpl
from app.modules.midagri.repository.interface.price_repository import MarketRepository, PriceRepository


def get_market_repository(session: MssqlSessionDep) -> MarketRepository:
    """Repositorio de mercados."""
    return MarketRepositoryImpl(session)


def get_price_repository(session: MssqlSessionDep) -> PriceRepository:
    """Repositorio de precios (misma sesión de SQL Server que el catálogo y el ubigeo en la solicitud)."""
    return PriceRepositoryImpl(session)


MarketRepositoryDep = Annotated[MarketRepository, Depends(get_market_repository)]
PriceRepositoryDep = Annotated[PriceRepository, Depends(get_price_repository)]
