"""Ejecuciones, eventos, cargas y reportes de faltantes en PostgreSQL."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.repository.impl.generic_repository_impl import GenericRepositoryImpl
from app.modules.midagri.model.pg import EtlRun, EtlRunEvent, GapReport, PriceLoad
from app.modules.midagri.model.pg.enums import ACTIVE_RUN_STATUSES, EventLevel, RunStatus
from app.modules.midagri.repository.interface.etl_run_repository import (
    EtlRunEventRepository,
    EtlRunRepository,
    GapReportRepository,
    PriceLoadRepository,
)

_LEVEL_ORDER = [EventLevel.DEBUG, EventLevel.INFO, EventLevel.WARNING, EventLevel.ERROR]


class EtlRunRepositoryImpl(GenericRepositoryImpl[EtlRun], EtlRunRepository):
    """Ejecuciones en PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(EtlRun, session)

    async def list_recent(self, page: int, size: int) -> tuple[list[EtlRun], int]:
        total = await self.count()
        stmt = select(EtlRun).order_by(EtlRun.id.desc()).offset((page - 1) * size).limit(size)
        return list(await self.session.scalars(stmt)), total

    async def get_active(self) -> EtlRun | None:
        stmt = select(EtlRun).where(EtlRun.status.in_(ACTIVE_RUN_STATUSES)).limit(1)
        return (await self.session.scalars(stmt)).first()

    async def fail_interrupted(self, message: str) -> int:
        now = datetime.now(UTC)
        stmt = (
            update(EtlRun)
            .where(EtlRun.status.in_(ACTIVE_RUN_STATUSES))
            .values(status=RunStatus.FAILED, error=message, finished_at=now, updated_at=now)
        )
        return (await self.session.execute(stmt)).rowcount  # ty: ignore[unresolved-attribute]


class EtlRunEventRepositoryImpl(GenericRepositoryImpl[EtlRunEvent], EtlRunEventRepository):
    """Eventos del logger en PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(EtlRunEvent, session)

    async def list_for_run(self, etl_run_id: int, *, min_level: EventLevel, limit: int) -> list[EtlRunEvent]:
        levels = _LEVEL_ORDER[_LEVEL_ORDER.index(min_level) :]
        stmt = (
            select(EtlRunEvent)
            .where(EtlRunEvent.etl_run_id == etl_run_id, EtlRunEvent.level.in_(levels))
            .order_by(EtlRunEvent.id)
            .limit(limit)
        )
        return list(await self.session.scalars(stmt))


class PriceLoadRepositoryImpl(GenericRepositoryImpl[PriceLoad], PriceLoadRepository):
    """Cargas por mercado en PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PriceLoad, session)

    async def list_by_run(self, etl_run_id: int) -> list[PriceLoad]:
        stmt = select(PriceLoad).where(PriceLoad.etl_run_id == etl_run_id).order_by(PriceLoad.market_code)
        return list(await self.session.scalars(stmt))


class GapReportRepositoryImpl(GenericRepositoryImpl[GapReport], GapReportRepository):
    """Reportes de faltantes en PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(GapReport, session)

    async def latest(self) -> GapReport | None:
        stmt = select(GapReport).order_by(GapReport.id.desc()).limit(1)
        return (await self.session.scalars(stmt)).first()
