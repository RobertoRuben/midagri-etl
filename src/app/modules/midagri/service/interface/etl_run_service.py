"""Contratos de las ejecuciones, el reporte de faltantes guardado, los mercados y el health."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.modules.common.pagination.paginated import Paginated
from app.modules.midagri.dto.request.etl_run_request import EtlRunCreateRequest
from app.modules.midagri.dto.response.etl_run_response import (
    EtlRunCreatedResponse,
    EtlRunDetailResponse,
    EtlRunSummaryResponse,
    LogEventResponse,
)
from app.modules.midagri.dto.response.gap_report_response import GapReportResponse
from app.modules.midagri.dto.response.health_response import HealthResponse
from app.modules.midagri.dto.response.market_response import MarketResponse
from app.modules.midagri.model.pg.enums import EventLevel


class EtlRunService(ABC):
    """Ejecuciones del ETL: alta (la corrida la lanza el `EtlRunner`), consulta y log."""

    @abstractmethod
    async def create_run(self, request: EtlRunCreateRequest, requested_by: str | None) -> EtlRunCreatedResponse:
        """Registra una ejecución `queued`.

        Raises:
            BadRequestException: Si algún mercado pedido no existe o no está activo.
            ConflictException: Si ya hay una ejecución `queued` o `running`.
        """

    @abstractmethod
    async def list_runs(self, page: int, size: int) -> Paginated[EtlRunSummaryResponse]:
        """Ejecuciones, la más reciente primero."""

    @abstractmethod
    async def get_run(self, etl_run_id: int) -> EtlRunDetailResponse:
        """Detalle con el resultado por mercado.

        Raises:
            NotFoundException: Si la ejecución no existe.
        """

    @abstractmethod
    async def get_logs(self, etl_run_id: int, min_level: EventLevel, limit: int) -> list[LogEventResponse]:
        """Eventos de la ejecución desde `min_level`.

        Raises:
            NotFoundException: Si la ejecución no existe.
        """


@dataclass(frozen=True, slots=True)
class ExcelFile:
    """Archivo Excel listo para descargar."""

    filename: str
    content: bytes


class GapReportService(ABC):
    """Último reporte de faltantes calculado (D27)."""

    @abstractmethod
    async def latest(self) -> GapReportResponse:
        """Raises: NotFoundException si todavía no hay reportes."""

    @abstractmethod
    async def latest_excel(self) -> ExcelFile:
        """Raises: NotFoundException si todavía no hay reportes."""


class MarketService(ABC):
    """Mercados de `BM_Market`."""

    @abstractmethod
    async def list_all(self) -> list[MarketResponse]:
        """Todos los mercados, activos primero."""


class HealthService(ABC):
    """Estado de SQL Server, PostgreSQL y el portal SISAP."""

    @abstractmethod
    async def check(self) -> HealthResponse:
        """Nunca lanza: cada dependencia caída queda como `error` y el estado general como `degraded`."""
