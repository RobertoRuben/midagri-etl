"""Respuestas del registro de faltantes desde la hoja `Registro` (D33)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.modules.midagri.model.pg.enums import CatalogLoadStatus, RegistrationOutcome


class CatalogRegistrationItemResponse(BaseModel):
    """Una fila de la hoja y lo que pasó con ella."""

    model_config = ConfigDict(from_attributes=True)

    kind: Literal["crop", "product"] = "product"
    """`crop`: fila de la hoja `Cultivos`; `product`: fila de la hoja `Registro`."""
    row_number: int
    code: str
    name: str
    crop_code: str
    outcome: RegistrationOutcome
    detail: str | None = None


class CatalogRegistrationSummaryResponse(BaseModel):
    """Una subida del Excel, sin sus filas."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    file_name: str
    requested_by: str | None = None
    dry_run: bool
    status: CatalogLoadStatus
    total_rows: int
    planned: int
    created: int
    skipped: int
    invalid: int
    errors: int
    error: str | None = None
    etl_run_id: int | None = None
    """Ejecución del ETL que hizo el alta automática (D36); `None` en las subidas del Excel."""


class CatalogRegistrationResponse(CatalogRegistrationSummaryResponse):
    """Una subida del Excel con el resultado de cada fila."""

    items: list[CatalogRegistrationItemResponse]
