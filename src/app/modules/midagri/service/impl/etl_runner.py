"""Ejecución del ETL en segundo plano: ingesta por mercado → faltantes → correos, con su log en PostgreSQL.

Corre fuera de la solicitud HTTP (la sesión de la solicitud ya se cerró), así que abre sus propias sesiones de
PostgreSQL y SQL Server y su cliente del portal. Las fábricas se inyectan para poder probarlo con otras bases.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
import polars as pl
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.common.config import base_config
from app.modules.midagri.dto.response.etl_run_response import (
    EtlRunDetailResponse,
    LogEventResponse,
    PriceLoadResponse,
)
from app.modules.midagri.dto.response.gap_report_response import GapReportResponse
from app.modules.midagri.model.mssql import Market
from app.modules.midagri.model.pg import EtlRun, EtlRunEvent, GapReport, PriceLoad
from app.modules.midagri.model.pg.enums import EventLevel, LoadStatus, MailStatus, RunStatus
from app.modules.midagri.model.sisap import MarketRef
from app.modules.midagri.repository.impl.catalog_load_repository_impl import CatalogLoadRepositoryImpl
from app.modules.midagri.repository.impl.catalog_repository_impl import CatalogRepositoryImpl
from app.modules.midagri.repository.impl.crop_repository_impl import CropRepositoryImpl
from app.modules.midagri.repository.impl.etl_run_repository_impl import (
    EtlRunEventRepositoryImpl,
    EtlRunRepositoryImpl,
    GapReportRepositoryImpl,
    PriceLoadRepositoryImpl,
)
from app.modules.midagri.repository.impl.mail_repository_impl import MailLogRepositoryImpl, MailRecipientRepositoryImpl
from app.modules.midagri.repository.impl.price_repository_impl import MarketRepositoryImpl, PriceRepositoryImpl
from app.modules.midagri.repository.impl.sisap_repository_impl import SisapRepositoryImpl
from app.modules.midagri.repository.impl.ubigeo_repository_impl import UbigeoRepositoryImpl
from app.modules.midagri.repository.interface.mail_repository import MailSender
from app.modules.midagri.repository.interface.price_repository import REPORT_MARKET_CODE
from app.modules.midagri.service.impl.catalog_registration_service_impl import CatalogRegistrationServiceImpl
from app.modules.midagri.service.impl.gap_service_impl import GapServiceImpl
from app.modules.midagri.service.impl.ingestion_service_impl import IngestionServiceImpl
from app.modules.midagri.service.impl.notification_service_impl import EmailNotificationServiceImpl
from app.modules.midagri.service.interface.ingestion_service import MarketIngestion
from app.modules.midagri.service.interface.notification_service import MailAttachment
from app.modules.midagri.utils.dates import default_window
from app.modules.midagri.utils.excel_writer import build_gap_workbook, gap_excel_filename
from app.modules.midagri.utils.trace import format_trace

logger = logging.getLogger(__name__)

INTERRUPTED = "Interrumpida por reinicio del servicio."
MAX_EVENT_EXAMPLES = 20
MAX_INCIDENTS = 500
"""Eventos que se leen para el correo de incidencias; la plantilla muestra los primeros y cuenta el resto."""
INCIDENT_EXCLUDED_PREFIXES = ("mail.", "run.end")
"""Avisos de los propios correos y el resumen final: no son incidencias del proceso."""


class RunJournal:
    """Escribe eventos en `etl_run_event`, cada uno en su propia transacción corta (visible mientras corre)."""

    def __init__(self, session: AsyncSession, etl_run_id: int) -> None:
        self._repository = EtlRunEventRepositoryImpl(session)
        self._session = session
        self._etl_run_id = etl_run_id

    async def log(
        self,
        level: EventLevel,
        event: str,
        message: str,
        *,
        market_code: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        logger.log(logging.getLevelNamesMapping()[level.value], "[run %s] %s", self._etl_run_id, message)
        try:
            await self._repository.save(
                EtlRunEvent(
                    etl_run_id=self._etl_run_id,
                    level=level,
                    event=event,
                    message=message,
                    market_code=market_code,
                    data=data,
                )
            )
            await self._session.commit()
        except Exception:  # el log nunca tumba la ejecución
            await self._session.rollback()
            logger.exception("[run %s] no se pudo registrar el evento %s", self._etl_run_id, event)


class EtlRunner:
    """Lanza y ejecuta corridas del ETL en segundo plano, y recuerda las tareas para cancelarlas al apagar.

    Args:
        pg_sessions: Fábrica de sesiones de PostgreSQL.
        mssql_sessions: Fábrica de sesiones de SQL Server.
        sisap_client: Crea el cliente HTTP del portal (se cierra al terminar cada corrida).
        mail_sender: Crea el envío de correos (Microsoft Graph).
    """

    def __init__(
        self,
        *,
        pg_sessions: async_sessionmaker[AsyncSession],
        mssql_sessions: async_sessionmaker[AsyncSession],
        sisap_client: Callable[[], httpx.AsyncClient],
        mail_sender: Callable[[], MailSender],
    ) -> None:
        self._pg_sessions = pg_sessions
        self._mssql_sessions = mssql_sessions
        self._sisap_client = sisap_client
        self._mail_sender = mail_sender
        self._tasks: set[asyncio.Task[None]] = set()
        self._gap_refresh: asyncio.Task[None] | None = None

    def start(self, etl_run_id: int) -> asyncio.Task[None]:
        """Programa la corrida en segundo plano y devuelve la tarea."""
        task = asyncio.create_task(self.execute(etl_run_id), name=f"etl-run-{etl_run_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def recover(self) -> int:
        """Al arrancar: las corridas que quedaron `queued`/`running` se marcan `failed` (reinicio)."""
        async with self._pg_sessions() as session:
            count = await EtlRunRepositoryImpl(session).fail_interrupted(INTERRUPTED)
            await session.commit()
        if count:
            logger.warning("%s ejecuciones interrumpidas por reinicio marcadas como failed", count)
        return count

    async def shutdown(self) -> None:
        """Al apagar: cancela las corridas en curso (quedan `failed` al volver a arrancar)."""
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def start_gap_refresh(self) -> bool:
        """Recalcula los faltantes en segundo plano (portal en vivo, D27). `False` si ya hay un recálculo en curso."""
        if self._gap_refresh is not None and not self._gap_refresh.done():
            return False
        self._gap_refresh = asyncio.create_task(self.refresh_gaps(), name="gap-refresh")
        self._tasks.add(self._gap_refresh)
        self._gap_refresh.add_done_callback(self._tasks.discard)
        return True

    async def refresh_gaps(self) -> None:
        """Faltantes de los mercados activos en la ventana por defecto, guardados sin ejecución asociada."""
        try:
            async with self._pg_sessions() as pg, self._mssql_sessions() as mssql, self._sisap_client() as client:
                active = await MarketRepositoryImpl(mssql).list_active()
                markets = [_market_ref(market) for market in active]
                date_from, date_to = default_window(base_config.etl_default_window_days)
                sisap = SisapRepositoryImpl(client, concurrency=base_config.sisap_concurrency)
                service = GapServiceImpl(sisap, CropRepositoryImpl(mssql), CatalogRepositoryImpl(mssql))
                report = await service.build_report(markets, date_from, date_to)
                await GapReportRepositoryImpl(pg).save(_gap_report(None, report))
                await pg.commit()
                logger.info("Faltantes recalculados: %s ESC2, %s ESC1", report.total_esc2, report.total_esc1)
        except Exception:
            logger.exception("No se pudo recalcular el reporte de faltantes")

    async def execute(self, etl_run_id: int) -> None:
        """Corre una ejecución completa. Nunca lanza: cualquier fallo deja la ejecución `failed`."""
        started = time.monotonic()
        async with self._pg_sessions() as pg, self._mssql_sessions() as mssql, self._sisap_client() as client:
            runs = EtlRunRepositoryImpl(pg)
            run = await runs.get_by_id(etl_run_id)
            if run is None:
                logger.error("La ejecución %s no existe", etl_run_id)
                return
            journal = RunJournal(pg, run.id)
            notifier = EmailNotificationServiceImpl(
                MailRecipientRepositoryImpl(pg),
                MailLogRepositoryImpl(pg),
                self._mail_sender(),
                enabled=base_config.mail_enabled,
                mail_from=base_config.mail_from,
                api_public_url=base_config.api_public_url,
                catalog_auto_register=base_config.catalog_auto_register,
            )
            sisap = SisapRepositoryImpl(
                client, concurrency=base_config.sisap_concurrency, retries=base_config.sisap_retries
            )
            attachment: MailAttachment | None = None
            market_names: dict[str, str] = {}
            try:
                run.status, run.started_at = RunStatus.RUNNING, datetime.now(UTC)
                await pg.commit()
                window = f"{run.date_from:%d/%m/%Y} al {run.date_to:%d/%m/%Y}"
                await journal.log(
                    EventLevel.INFO,
                    "run.start",
                    f"Inicio{' (dry_run)' if run.dry_run else ''}: {window}, mercados {', '.join(run.market_codes)}",
                )
                try:
                    market_names = await self._market_names(mssql, run.market_codes)
                except Exception:
                    await mssql.rollback()
                    logger.exception("No se pudieron consultar los nombres de mercados de la ejecución %s", run.id)
                    await journal.log(
                        EventLevel.WARNING,
                        "mail.market_names",
                        "No se pudieron consultar los nombres de mercados; el correo mostrará los códigos.",
                    )
                mail_status = await notifier.notify_start(await self._detail(pg, run), market_names=market_names)
                if mail_status is not MailStatus.SENT:
                    await journal.log(EventLevel.WARNING, "mail.start", f"Correo de inicio: {mail_status.value}")
                await pg.refresh(run)  # un rollback al registrar el correo puede expirar la entidad

                ingestions = await self._ingest_markets(run, mssql, sisap, pg, journal)
                attachment, report = await self._gaps(run, ingestions, mssql, sisap, pg, journal)
                if report is not None and base_config.catalog_auto_register:
                    await self._register_gaps(run, report, mssql, pg, journal)
                self._close(run, ingestions)
            except asyncio.CancelledError:
                run.status, run.error = RunStatus.FAILED, INTERRUPTED
                raise
            except Exception as error:
                logger.exception("La ejecución %s falló", etl_run_id)
                await pg.rollback()  # expira `run`: en async hay que recargarlo antes de leerlo
                await pg.refresh(run)
                run.status, run.error = RunStatus.FAILED, f"{type(error).__name__}: {error}"
                await journal.log(EventLevel.ERROR, "run.error", f"La ejecución falló: {run.error}", data=_trace_data())
            finally:
                duration_ms = round((time.monotonic() - started) * 1000)
                run.finished_at, run.duration_ms = datetime.now(UTC), duration_ms
                await pg.commit()
            await journal.log(
                EventLevel.INFO if run.status is RunStatus.OK else EventLevel.WARNING,
                "run.end",
                f"Fin: {run.status.value} en {duration_ms / 1000:.1f} s — {run.inserted} nuevas, "
                f"{run.updated} actualizadas, {run.unmatched} sin catálogo, {run.rejected} rechazadas",
            )
            detail = await self._detail(pg, run)
            mail_status = await notifier.notify_end(detail, attachment, market_names=market_names)
            if mail_status is not MailStatus.SENT:
                await journal.log(EventLevel.WARNING, "mail.end", f"Correo de fin: {mail_status.value}")
            incidents = await self._incidents(pg, run.id)
            if incidents:
                mail_status = await notifier.notify_errors(detail, incidents, market_names=market_names)
                if mail_status is not MailStatus.SENT:
                    await journal.log(EventLevel.WARNING, "mail.error", f"Correo de incidencias: {mail_status.value}")

    async def _ingest_markets(
        self, run: EtlRun, mssql: AsyncSession, sisap: SisapRepositoryImpl, pg: AsyncSession, journal: RunJournal
    ) -> list[MarketIngestion]:
        markets = MarketRepositoryImpl(mssql)
        ingestion = IngestionServiceImpl(
            sisap,
            CropRepositoryImpl(mssql),
            CatalogRepositoryImpl(mssql),
            UbigeoRepositoryImpl(mssql),
            PriceRepositoryImpl(mssql),
        )
        loads = PriceLoadRepositoryImpl(pg)
        results: list[MarketIngestion] = []
        for code in run.market_codes:
            market = await markets.get_by_code(code)
            if market is None:
                await journal.log(EventLevel.ERROR, "market.missing", f"El mercado {code} no existe en BM_Market")
                continue
            await journal.log(EventLevel.INFO, "market.start", f"{market.name} ({code})", market_code=code)
            result = await ingestion.ingest_market(market, run.date_from, run.date_to, dry_run=run.dry_run)
            results.append(result)
            await loads.save(_price_load(run.id, result))
            await pg.commit()
            await self._log_market(journal, market, result)
        return results

    async def _log_market(self, journal: RunJournal, market: Market, result: MarketIngestion) -> None:
        code = market.code
        if result.status is LoadStatus.FAILED:
            await journal.log(
                EventLevel.ERROR,
                "market.failed",
                f"{code}: {result.error}",
                market_code=code,
                data={"traceback": result.traceback} if result.traceback else None,
            )
            return
        if result.status is LoadStatus.SKIPPED:
            await journal.log(EventLevel.WARNING, "market.skipped", f"{code}: {result.error}", market_code=code)
            return
        for message in result.fetch_errors[:MAX_EVENT_EXAMPLES]:
            await journal.log(EventLevel.WARNING, "batch.error", message, market_code=code)
        if result.unmatched_codes:
            await journal.log(
                EventLevel.INFO,
                "prices.unmatched",
                f"{code}: {result.unmatched} precios sin producto activo en el catálogo "
                f"({len(result.unmatched_codes)} códigos)",
                market_code=code,
                data={"codes": result.unmatched_codes},
            )
        if not result.rejected.is_empty():
            by_reason = result.rejected.group_by("reason").agg(pl.len().alias("rows")).sort("reason")
            examples = result.rejected.head(MAX_EVENT_EXAMPLES).with_columns(
                pl.col(pl.Date, pl.Decimal).cast(pl.String)
            )
            await journal.log(
                EventLevel.WARNING,
                "prices.rejected",
                f"{code}: {result.rejected.height} precios rechazados por calidad",
                market_code=code,
                data={"by_reason": dict(by_reason.iter_rows()), "examples": examples.to_dicts()},
            )
        await journal.log(
            EventLevel.INFO,
            "market.done",
            f"{code}: {result.fetched} descargadas, {result.matched} cargables, {result.inserted} nuevas, "
            f"{result.updated} actualizadas, {result.unchanged} sin cambios ({result.status.value})",
            market_code=code,
        )
        if code == REPORT_MARKET_CODE:
            await journal.log(
                EventLevel.INFO,
                "report.done",
                f"{code}: BM_CatalogPrice (reporte del app) {result.report_inserted} nuevas, "
                f"{result.report_updated} actualizadas",
                market_code=code,
            )

    async def _gaps(
        self,
        run: EtlRun,
        ingestions: Sequence[MarketIngestion],
        mssql: AsyncSession,
        sisap: SisapRepositoryImpl,
        pg: AsyncSession,
        journal: RunJournal,
    ) -> tuple[MailAttachment | None, GapReportResponse | None]:
        """Faltantes con los precios ya descargados (D27). Si falla, la ejecución sigue: queda `partial`."""
        usable = [result for result in ingestions if result.status is not LoadStatus.FAILED]
        if not usable:
            return None, None
        try:
            service = GapServiceImpl(sisap, CropRepositoryImpl(mssql), CatalogRepositoryImpl(mssql))
            report = await service.build_report_from_priced(
                [result.market for result in usable],
                run.date_from,
                run.date_to,
                [result.priced for result in usable],
                [message for result in usable for message in result.fetch_errors],
            )
            saved = await GapReportRepositoryImpl(pg).save(_gap_report(run.id, report))
            run.gaps_esc1, run.gaps_esc2 = report.total_esc1, report.total_esc2
            await pg.commit()
        except Exception as error:
            await pg.rollback()  # expira `run`: en async hay que recargarlo antes de leerlo
            await pg.refresh(run)
            message = f"Faltantes no calculados: {type(error).__name__}: {error}"
            run.error = message
            await journal.log(EventLevel.ERROR, "gaps.error", message, data=_trace_data())
            return None, None
        await journal.log(
            EventLevel.INFO,
            "gaps.done",
            f"Faltantes: {report.total_esc2} variedades (ESC2) y {report.total_esc1} de cultivos nuevos (ESC1)",
        )
        return MailAttachment(filename=saved.excel_filename, content=saved.excel), report

    async def _register_gaps(
        self, run: EtlRun, report: GapReportResponse, mssql: AsyncSession, pg: AsyncSession, journal: RunJournal
    ) -> None:
        """Alta automática de los faltantes en el catálogo (D36). Nunca lanza: si falla, la ejecución queda `partial`.

        Solo entran faltantes vistos en al menos un mercado activo **ahora** (se vuelve a leer `BM_Market`) y no
        excluido. Con `dry_run` solo se guarda el plan.
        """
        try:
            active = await MarketRepositoryImpl(mssql).list_active()
            labels = {
                _market_ref(market).label for market in active if market.code not in base_config.etl_excluded_markets
            }
            items = [item for item in report.items if labels.intersection(item.markets)]
            if len(items) < len(report.items):
                await journal.log(
                    EventLevel.INFO,
                    "catalog.skipped_markets",
                    f"{len(report.items) - len(items)} faltantes solo de mercados inactivos: no se registran",
                    data={"codes": sorted({i.variety_code for i in report.items} - {i.variety_code for i in items})},
                )
            if not items:
                return
            service = CatalogRegistrationServiceImpl(
                CatalogRepositoryImpl(mssql),
                CropRepositoryImpl(mssql),
                CatalogLoadRepositoryImpl(pg),
                mssql=mssql,
                pg=pg,
            )
            result = await service.register_gaps(items, etl_run_id=run.id, dry_run=run.dry_run)
        except Exception as error:
            await mssql.rollback()
            await pg.rollback()  # expira `run`: en async hay que recargarlo antes de leerlo
            await pg.refresh(run)
            message = f"Alta de faltantes no realizada: {type(error).__name__}: {error}"
            run.error = run.error or message
            await journal.log(EventLevel.ERROR, "catalog.error", message, data=_trace_data())
            return
        crops = [item for item in result.items if item.kind == "crop"]
        products = [item for item in result.items if item.kind == "product"]
        verb = "planificados" if run.dry_run else "creados"
        done = result.planned if run.dry_run else result.created
        summary = (
            f"Catálogo ({result.status.value}): {done} {verb} de {len(crops)} cultivos y {len(products)} productos; "
            f"{result.skipped} ya existían, {result.invalid} inválidos, {result.errors} con error"
        )
        failed = result.invalid or result.errors
        if failed:
            run.error = run.error or summary
        await journal.log(
            EventLevel.WARNING if failed else EventLevel.INFO,
            "catalog.registered",
            summary,
            data={"catalog_load_id": result.id, "codes": [item.code for item in result.items]},
        )

    @staticmethod
    def _close(run: EtlRun, ingestions: Sequence[MarketIngestion]) -> None:
        """Totales y estado final: `failed` si ningún mercado cargó; `partial` si alguno falló o quedó incompleto."""
        run.fetched = sum(result.fetched for result in ingestions)
        run.matched = sum(result.matched for result in ingestions)
        run.inserted = sum(result.inserted for result in ingestions)
        run.updated = sum(result.updated for result in ingestions)
        run.unmatched = sum(result.unmatched for result in ingestions)
        run.rejected = sum(result.rejected.height for result in ingestions)
        run.errors = sum(len(result.fetch_errors) + (result.status is LoadStatus.FAILED) for result in ingestions)
        statuses = {result.status for result in ingestions}
        if not ingestions or statuses <= {LoadStatus.FAILED}:
            run.status = RunStatus.FAILED
            run.error = run.error or "Ningún mercado se pudo cargar."
        elif statuses & {LoadStatus.FAILED, LoadStatus.PARTIAL} or run.error:
            run.status = RunStatus.PARTIAL
        else:
            run.status = RunStatus.OK

    @staticmethod
    async def _market_names(mssql: AsyncSession, codes: Sequence[str]) -> dict[str, str]:
        """Consulta los nombres de los mercados de la ejecución antes de enviar el primer correo."""
        markets = MarketRepositoryImpl(mssql)
        names: dict[str, str] = {}
        for code in codes:
            market = await markets.get_by_code(code)
            if market is not None:
                names[code] = market.name
        return names

    @staticmethod
    async def _incidents(pg: AsyncSession, etl_run_id: int) -> list[LogEventResponse]:
        """Errores y advertencias de la ejecución para el correo de incidencias (D37), sin los avisos de correo."""
        try:
            events = await EtlRunEventRepositoryImpl(pg).list_for_run(
                etl_run_id, min_level=EventLevel.WARNING, limit=MAX_INCIDENTS
            )
        except Exception:  # sin log no hay correo de incidencias, pero la ejecución ya terminó
            await pg.rollback()
            logger.exception("No se pudo leer el log de incidencias de la ejecución %s", etl_run_id)
            return []
        return [
            LogEventResponse.model_validate(event)
            for event in events
            if not event.event.startswith(INCIDENT_EXCLUDED_PREFIXES)
        ]

    @staticmethod
    async def _detail(pg: AsyncSession, run: EtlRun) -> EtlRunDetailResponse:
        loads = await PriceLoadRepositoryImpl(pg).list_by_run(run.id)
        detail = EtlRunDetailResponse.model_validate(run)
        return detail.model_copy(update={"loads": [PriceLoadResponse.model_validate(load) for load in loads]})


def _trace_data() -> dict[str, Any] | None:
    """`data` de un evento de error con la traza de la excepción en curso (D37)."""
    trace = format_trace()
    return {"traceback": trace} if trace else None


def _market_ref(market: Market) -> MarketRef:
    return MarketRef("CIUDADES" if market.source == "CIUDADES" else "MAYORISTA", market.code, market.name)


def _price_load(etl_run_id: int, result: MarketIngestion) -> PriceLoad:
    return PriceLoad(
        etl_run_id=etl_run_id,
        market_code=result.market.code,
        status=result.status,
        date_from=result.date_from,
        date_to=result.date_to,
        fetched=result.fetched,
        matched=result.matched,
        inserted=result.inserted,
        updated=result.updated,
        unmatched=result.unmatched,
        errors=len(result.fetch_errors),
        rejected=result.rejected.height,
        unmatched_codes=result.unmatched_codes or None,
        started_at=result.started_at,
        finished_at=result.finished_at,
        error=result.error,
    )


def _gap_report(etl_run_id: int | None, report: GapReportResponse) -> GapReport:
    return GapReport(
        etl_run_id=etl_run_id,
        date_from=report.date_from,
        date_to=report.date_to,
        markets=report.markets,
        total_esc1=report.total_esc1,
        total_esc2=report.total_esc2,
        warnings=len(report.warnings),
        report=report.model_dump(mode="json"),
        excel_filename=gap_excel_filename(report),
        excel=build_gap_workbook(report),
    )
