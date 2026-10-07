"""Dependencias FastAPI de ejecuciones, eventos, cargas y reportes de faltantes (PostgreSQL)."""

from typing import Annotated

from fastapi import Depends

from app.modules.common.db.dependencies import PgSessionDep
from app.modules.midagri.repository.impl.etl_run_repository_impl import (
    EtlRunEventRepositoryImpl,
    EtlRunRepositoryImpl,
    GapReportRepositoryImpl,
    PriceLoadRepositoryImpl,
)
from app.modules.midagri.repository.interface.etl_run_repository import (
    EtlRunEventRepository,
    EtlRunRepository,
    GapReportRepository,
    PriceLoadRepository,
)


def get_etl_run_repository(session: PgSessionDep) -> EtlRunRepository:
    """Ejecuciones."""
    return EtlRunRepositoryImpl(session)


def get_etl_run_event_repository(session: PgSessionDep) -> EtlRunEventRepository:
    """Logger."""
    return EtlRunEventRepositoryImpl(session)


def get_price_load_repository(session: PgSessionDep) -> PriceLoadRepository:
    """Cargas por mercado."""
    return PriceLoadRepositoryImpl(session)


def get_gap_report_repository(session: PgSessionDep) -> GapReportRepository:
    """Reportes de faltantes."""
    return GapReportRepositoryImpl(session)


EtlRunRepositoryDep = Annotated[EtlRunRepository, Depends(get_etl_run_repository)]
EtlRunEventRepositoryDep = Annotated[EtlRunEventRepository, Depends(get_etl_run_event_repository)]
PriceLoadRepositoryDep = Annotated[PriceLoadRepository, Depends(get_price_load_repository)]
GapReportRepositoryDep = Annotated[GapReportRepository, Depends(get_gap_report_repository)]
