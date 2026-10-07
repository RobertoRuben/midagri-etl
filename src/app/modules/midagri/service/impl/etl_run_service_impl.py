"""Ejecuciones, reporte de faltantes guardado, mercados y health."""

import asyncio
from datetime import timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.config import base_config
from app.modules.common.db.decorator.transactional import transactional
from app.modules.common.exception import BadRequestException, ConflictException, NotFoundException
from app.modules.common.pagination.paginated import Paginated
from app.modules.common.pagination.pagination_meta import PaginationMeta
from app.modules.midagri.dto.request.etl_run_request import EtlRunCreateRequest
from app.modules.midagri.dto.response.etl_run_response import (
    EtlRunCreatedResponse,
    EtlRunDetailResponse,
    EtlRunSummaryResponse,
    LogEventResponse,
    PriceLoadResponse,
)
from app.modules.midagri.dto.response.gap_report_response import GapReportResponse
from app.modules.midagri.dto.response.health_response import CheckStatus, HealthResponse
from app.modules.midagri.dto.response.market_response import MarketResponse
from app.modules.midagri.model.pg import EtlRun, GapReport
from app.modules.midagri.model.pg.enums import EventLevel, RunStatus
from app.modules.midagri.repository.interface.etl_run_repository import (
    EtlRunEventRepository,
    EtlRunRepository,
    GapReportRepository,
    PriceLoadRepository,
)
from app.modules.midagri.repository.interface.price_repository import MarketRepository
from app.modules.midagri.service.interface.etl_run_service import (
    EtlRunService,
    ExcelFile,
    GapReportService,
    HealthService,
    MarketService,
)
from app.modules.midagri.utils.dates import today_lima


class EtlRunServiceImpl(EtlRunService):
    """Alta y consulta de ejecuciones (PostgreSQL); valida los mercados contra `BM_Market` (SQL Server)."""

    __session_attr__ = "run_repository.session"

    def __init__(
        self,
        run_repository: EtlRunRepository,
        load_repository: PriceLoadRepository,
        event_repository: EtlRunEventRepository,
        market_repository: MarketRepository,
    ) -> None:
        self.run_repository = run_repository
        self.load_repository = load_repository
        self.event_repository = event_repository
        self.market_repository = market_repository

    async def create_run(self, request: EtlRunCreateRequest, requested_by: str | None) -> EtlRunCreatedResponse:
        active = [market.code for market in await self.market_repository.list_active()]
        codes = request.market_codes or active
        invalid = sorted(set(codes) - set(active))
        if invalid:
            raise BadRequestException(f"Mercados inexistentes o inactivos en BM_Market: {', '.join(invalid)}")
        date_to = request.date_to or today_lima()
        date_from = request.date_from or date_to - timedelta(days=base_config.etl_default_window_days)
        if date_from > date_to:
            raise BadRequestException("date_from no puede ser posterior a date_to")
        run = await self._insert(
            EtlRun(
                status=RunStatus.QUEUED,
                trigger=request.trigger,
                requested_by=requested_by,
                dry_run=request.dry_run,
                date_from=date_from,
                date_to=date_to,
                market_codes=sorted(set(codes)),
            )
        )
        return EtlRunCreatedResponse(id=run.id, status=run.status)

    @transactional
    async def _insert(self, run: EtlRun) -> EtlRun:
        try:
            return await self.run_repository.save(run)
        except IntegrityError as exc:
            if "uq_etl_run_active" not in str(exc):
                raise
            raise ConflictException("Ya hay una ejecución en curso; espere a que termine.") from exc

    async def list_runs(self, page: int, size: int) -> Paginated[EtlRunSummaryResponse]:
        runs, total = await self.run_repository.list_recent(page, size)
        return Paginated[EtlRunSummaryResponse](
            data=[EtlRunSummaryResponse.model_validate(run) for run in runs],
            pagination=PaginationMeta.build(page=page, page_size=size, total_items=total),
        )

    async def get_run(self, etl_run_id: int) -> EtlRunDetailResponse:
        run = await self._run(etl_run_id)
        loads = await self.load_repository.list_by_run(run.id)
        detail = EtlRunDetailResponse.model_validate(run)
        return detail.model_copy(update={"loads": [PriceLoadResponse.model_validate(load) for load in loads]})

    async def get_logs(self, etl_run_id: int, min_level: EventLevel, limit: int) -> list[LogEventResponse]:
        await self._run(etl_run_id)
        events = await self.event_repository.list_for_run(etl_run_id, min_level=min_level, limit=limit)
        return [LogEventResponse.model_validate(event) for event in events]

    async def _run(self, etl_run_id: int) -> EtlRun:
        run = await self.run_repository.get_by_id(etl_run_id)
        if run is None:
            raise NotFoundException(f"No existe la ejecución {etl_run_id}.")
        return run


class GapReportServiceImpl(GapReportService):
    """Último reporte de faltantes guardado en `gap_report`."""

    def __init__(self, gap_report_repository: GapReportRepository) -> None:
        self.gap_report_repository = gap_report_repository

    async def latest(self) -> GapReportResponse:
        report = await self._latest()
        return GapReportResponse.model_validate(report.report)

    async def latest_excel(self) -> ExcelFile:
        report = await self._latest()
        return ExcelFile(filename=report.excel_filename, content=report.excel)

    async def _latest(self) -> GapReport:
        report = await self.gap_report_repository.latest()
        if report is None:
            raise NotFoundException("Todavía no hay reportes de faltantes: se generan en cada ejecución del ETL.")
        return report


class MarketServiceImpl(MarketService):
    """Mercados de SQL Server."""

    def __init__(self, market_repository: MarketRepository) -> None:
        self.market_repository = market_repository

    async def list_all(self) -> list[MarketResponse]:
        markets = sorted(await self.market_repository.get_all(), key=lambda m: (not m.active, m.code))
        return [MarketResponse.model_validate(market) for market in markets]


class HealthServiceImpl(HealthService):
    """Consulta rápida a las dos bases y al portal, en paralelo y con timeout."""

    TIMEOUT_SECONDS = 10

    def __init__(self, mssql: AsyncSession, postgres: AsyncSession, sisap_base_url: str) -> None:
        self.mssql = mssql
        self.postgres = postgres
        self.sisap_base_url = sisap_base_url.rstrip("/")

    async def check(self) -> HealthResponse:
        checks = await asyncio.gather(
            self._database(self.mssql), self._database(self.postgres), self._sisap(), return_exceptions=False
        )
        (mssql, mssql_error), (postgres, postgres_error), (sisap, sisap_error) = checks
        details = {
            name: error
            for name, error in (("mssql", mssql_error), ("postgres", postgres_error), ("sisap", sisap_error))
            if error
        }
        healthy = mssql == postgres == sisap == "ok"
        return HealthResponse(
            status="ok" if healthy else "degraded", mssql=mssql, postgres=postgres, sisap=sisap, details=details
        )

    async def _database(self, session: AsyncSession) -> tuple[CheckStatus, str | None]:
        try:
            async with asyncio.timeout(self.TIMEOUT_SECONDS):
                await session.execute(text("SELECT 1"))
            return "ok", None
        except Exception as error:
            return "error", f"{type(error).__name__}: {error}"

    async def _sisap(self) -> tuple[CheckStatus, str | None]:
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                response = await client.get(f"{self.sisap_base_url}/mayorista/resumenes/consultar/")
                response.raise_for_status()
            return "ok", None
        except Exception as error:
            return "error", f"{type(error).__name__}: {error}"
