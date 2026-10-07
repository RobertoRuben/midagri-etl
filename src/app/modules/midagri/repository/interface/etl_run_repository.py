"""Contratos de ejecuciones, eventos, cargas y reportes de faltantes (PostgreSQL)."""

from typing import Protocol

from app.modules.common.repository.interface.generic_repository import GenericRepository
from app.modules.midagri.model.pg import EtlRun, EtlRunEvent, GapReport, PriceLoad
from app.modules.midagri.model.pg.enums import EventLevel


class EtlRunRepository(GenericRepository[EtlRun], Protocol):
    """Ejecuciones del ETL."""

    async def list_recent(self, page: int, size: int) -> tuple[list[EtlRun], int]:
        """Página de ejecuciones, la más reciente primero, y el total."""
        ...

    async def get_active(self) -> EtlRun | None:
        """La ejecución `queued` o `running`, si hay una."""
        ...

    async def fail_interrupted(self, message: str) -> int:
        """Marca como `failed` las ejecuciones que quedaron `queued`/`running` (reinicio). Devuelve cuántas."""
        ...


class EtlRunEventRepository(GenericRepository[EtlRunEvent], Protocol):
    """Logger de las ejecuciones."""

    async def list_for_run(self, etl_run_id: int, *, min_level: EventLevel, limit: int) -> list[EtlRunEvent]:
        """Eventos de una ejecución desde `min_level`, en orden, hasta `limit`."""
        ...


class PriceLoadRepository(GenericRepository[PriceLoad], Protocol):
    """Cargas por mercado."""

    async def list_by_run(self, etl_run_id: int) -> list[PriceLoad]:
        """Cargas de una ejecución, por mercado."""
        ...


class GapReportRepository(GenericRepository[GapReport], Protocol):
    """Reportes de faltantes calculados (D27)."""

    async def latest(self) -> GapReport | None:
        """El reporte más reciente."""
        ...
