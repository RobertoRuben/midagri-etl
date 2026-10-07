"""Solicitud para lanzar una ejecución del ETL."""

from datetime import date
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.modules.midagri.model.pg.enums import RunTrigger

MAX_WINDOW_DAYS = 366


class EtlRunCreateRequest(BaseModel):
    """Todo es opcional: sin cuerpo se cargan los mercados activos en la ventana por defecto (últimos 5 días).

    La tarea programada envía `{"trigger": "cron"}`.
    """

    date_from: date | None = None
    date_to: date | None = None
    market_codes: list[str] | None = Field(
        default=None, description="Códigos de `BM_Market` (activos). Sin valor: todos los activos."
    )
    dry_run: bool = Field(default=False, description="Descarga, valida y cuenta, pero no escribe en SQL Server.")
    trigger: RunTrigger = RunTrigger.MANUAL

    @model_validator(mode="after")
    def _window(self) -> Self:
        if self.date_from and self.date_to:
            if self.date_from > self.date_to:
                raise ValueError("date_from no puede ser posterior a date_to")
            if (self.date_to - self.date_from).days >= MAX_WINDOW_DAYS:
                raise ValueError(f"La ventana no puede superar {MAX_WINDOW_DAYS} días")
        if self.market_codes is not None and not self.market_codes:
            raise ValueError("market_codes no puede ser una lista vacía")
        return self
