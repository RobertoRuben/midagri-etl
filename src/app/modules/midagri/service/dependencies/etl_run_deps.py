"""Dependencias FastAPI de ejecuciones, reporte de faltantes guardado, mercados, health y el runner."""

from typing import Annotated

from fastapi import Depends, Request

from app.modules.common.config import base_config
from app.modules.common.db.dependencies import MssqlSessionDep, PgSessionDep
from app.modules.midagri.repository.dependencies.etl_run_repository_deps import (
    EtlRunEventRepositoryDep,
    EtlRunRepositoryDep,
    GapReportRepositoryDep,
    PriceLoadRepositoryDep,
)
from app.modules.midagri.repository.dependencies.price_repository_deps import MarketRepositoryDep
from app.modules.midagri.service.impl.etl_run_service_impl import (
    EtlRunServiceImpl,
    GapReportServiceImpl,
    HealthServiceImpl,
    MarketServiceImpl,
)
from app.modules.midagri.service.impl.etl_runner import EtlRunner
from app.modules.midagri.service.interface.etl_run_service import (
    EtlRunService,
    GapReportService,
    HealthService,
    MarketService,
)


def get_etl_run_service(
    runs: EtlRunRepositoryDep,
    loads: PriceLoadRepositoryDep,
    events: EtlRunEventRepositoryDep,
    markets: MarketRepositoryDep,
) -> EtlRunService:
    """Alta y consulta de ejecuciones."""
    return EtlRunServiceImpl(runs, loads, events, markets)


def get_gap_report_service(reports: GapReportRepositoryDep) -> GapReportService:
    """Último reporte de faltantes."""
    return GapReportServiceImpl(reports)


def get_market_service(markets: MarketRepositoryDep) -> MarketService:
    """Mercados."""
    return MarketServiceImpl(markets)


def get_health_service(mssql: MssqlSessionDep, postgres: PgSessionDep) -> HealthService:
    """Health de las dos bases y el portal."""
    return HealthServiceImpl(mssql, postgres, base_config.sisap_base_url)


def get_etl_runner(request: Request) -> EtlRunner:
    """El runner vive en `app.state` (lo crea el `lifespan`): recuerda las corridas en curso."""
    return request.app.state.etl_runner


EtlRunServiceDep = Annotated[EtlRunService, Depends(get_etl_run_service)]
GapReportServiceDep = Annotated[GapReportService, Depends(get_gap_report_service)]
MarketServiceDep = Annotated[MarketService, Depends(get_market_service)]
HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
EtlRunnerDep = Annotated[EtlRunner, Depends(get_etl_runner)]
