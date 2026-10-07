"""Aplicación FastAPI de la API ETL SISAP-MIDAGRI."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.modules.common.config import base_config
from app.modules.common.db import MssqlSessionLocal, PgSessionLocal, dispose_engines
from app.modules.common.exception import register_exception_handlers
from app.modules.midagri.controller import (
    catalog_controller,
    catalog_registration_controller,
    etl_controller,
    health_controller,
    mail_recipient_controller,
    market_controller,
)
from app.modules.midagri.repository.dependencies.mail_repository_deps import get_mail_sender
from app.modules.midagri.repository.impl.sisap_repository_impl import build_sisap_client
from app.modules.midagri.service.impl.etl_runner import EtlRunner

logging.basicConfig(
    level=base_config.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app")

CONTROLLERS = (
    etl_controller,
    catalog_controller,
    catalog_registration_controller,
    market_controller,
    mail_recipient_controller,
    health_controller,
)


def build_etl_runner() -> EtlRunner:
    """Runner de producción: bases del `.env`, cliente del portal y envío de correos de la configuración."""
    return EtlRunner(
        pg_sessions=PgSessionLocal,
        mssql_sessions=MssqlSessionLocal,
        sisap_client=lambda: build_sisap_client(base_config.sisap_base_url, base_config.sisap_timeout_seconds),
        mail_sender=get_mail_sender,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Al arrancar marca como fallidas las corridas interrumpidas; al apagar cancela las que sigan y cierra pools."""
    runner: EtlRunner = getattr(app.state, "etl_runner", None) or build_etl_runner()
    app.state.etl_runner = runner
    await runner.recover()
    logger.info("API iniciada (ambiente=%s)", base_config.environment)
    yield
    await runner.shutdown()
    await dispose_engines()
    logger.info("API detenida")


app = FastAPI(
    title="API ETL SISAP-MIDAGRI",
    description="Ingesta multi-mercado de precios SISAP, faltantes de catálogo y logger de ejecuciones.",
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=[dict(controller.TAG) for controller in CONTROLLERS],
)

register_exception_handlers(app)
for controller in CONTROLLERS:
    app.include_router(controller.router)
