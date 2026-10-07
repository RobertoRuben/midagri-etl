"""Respuestas de las ejecuciones del ETL."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.midagri.model.pg.enums import EventLevel, LoadStatus, RunStatus, RunTrigger


class PriceLoadResponse(BaseModel):
    """Resultado de la carga de un mercado."""

    model_config = ConfigDict(from_attributes=True)

    market_code: str
    status: LoadStatus
    date_from: date
    date_to: date
    fetched: int
    matched: int
    inserted: int
    updated: int
    unmatched: int
    errors: int
    rejected: int = 0
    unmatched_codes: list[str] | None = None
    error: str | None = None


class EtlRunDetailResponse(BaseModel):
    """Ejecución del ETL con su resultado por mercado."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: RunStatus
    trigger: RunTrigger
    requested_by: str | None = None
    dry_run: bool = False
    date_from: date
    date_to: date
    market_codes: list[str]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    fetched: int
    matched: int
    inserted: int
    updated: int
    unmatched: int
    errors: int
    rejected: int = 0
    gaps_esc1: int | None = None
    gaps_esc2: int | None = None
    error: str | None = None
    loads: list[PriceLoadResponse] = []


class EtlRunCreatedResponse(BaseModel):
    """Ejecución aceptada: corre en segundo plano."""

    id: int
    status: RunStatus


class EtlRunSummaryResponse(BaseModel):
    """Ejecución en el listado (sin el detalle por mercado)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: RunStatus
    trigger: RunTrigger
    dry_run: bool
    date_from: date
    date_to: date
    market_codes: list[str]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    inserted: int
    updated: int
    unmatched: int
    rejected: int
    errors: int
    gaps_esc1: int | None = None
    gaps_esc2: int | None = None


class LogEventResponse(BaseModel):
    """Evento del logger de una ejecución."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    level: EventLevel
    event: str
    message: str
    market_code: str | None = None
    data: dict[str, Any] | None = None
