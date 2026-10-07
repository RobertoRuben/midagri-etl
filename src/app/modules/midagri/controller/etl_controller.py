"""`/etl/runs`: lanzar el ETL, historial y logger."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Request, status

from app.modules.common.pagination.paginated import Paginated
from app.modules.common.security.static_api_key import API_KEY_RESPONSES, require_api_key
from app.modules.common.types.api_responses import problem_response
from app.modules.common.types.openapi import TagMetadata
from app.modules.midagri.dto.request.etl_run_request import EtlRunCreateRequest
from app.modules.midagri.dto.response.etl_run_response import (
    EtlRunCreatedResponse,
    EtlRunDetailResponse,
    EtlRunSummaryResponse,
    LogEventResponse,
)
from app.modules.midagri.model.pg.enums import EventLevel
from app.modules.midagri.service.dependencies.etl_run_deps import EtlRunnerDep, EtlRunServiceDep

TAG: TagMetadata = {
    "name": "etl",
    "description": 'Lanza el ETL (lo llama la tarea programada con `{"trigger": "cron"}`), su historial y su log.',
}

router = APIRouter(
    prefix="/etl/runs",
    tags=["etl"],
    dependencies=[Depends(require_api_key)],
    responses=API_KEY_RESPONSES,
)

RunId = Annotated[int, Path(ge=1, description="Id de la ejecución")]


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_400_BAD_REQUEST: problem_response("Mercado inexistente o inactivo."),
        status.HTTP_409_CONFLICT: problem_response("Ya hay una ejecución en curso."),
    },
)
async def create_run(
    service: EtlRunServiceDep,
    runner: EtlRunnerDep,
    request: Request,
    body: Annotated[EtlRunCreateRequest | None, Body()] = None,
) -> EtlRunCreatedResponse:
    """Registra la ejecución y la corre en segundo plano. Responde enseguida; el avance se ve en `/logs`."""
    created = await service.create_run(body or EtlRunCreateRequest(), request.client.host if request.client else None)
    runner.start(created.id)
    return created


@router.get("")
async def list_runs(
    service: EtlRunServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Paginated[EtlRunSummaryResponse]:
    """Ejecuciones, la más reciente primero."""
    return await service.list_runs(page, size)


@router.get("/{etl_run_id}", responses={status.HTTP_404_NOT_FOUND: problem_response("La ejecución no existe.")})
async def get_run(service: EtlRunServiceDep, etl_run_id: RunId) -> EtlRunDetailResponse:
    """Detalle de una ejecución con el resultado de cada mercado."""
    return await service.get_run(etl_run_id)


@router.get("/{etl_run_id}/logs", responses={status.HTTP_404_NOT_FOUND: problem_response("La ejecución no existe.")})
async def get_logs(
    service: EtlRunServiceDep,
    etl_run_id: RunId,
    level: Annotated[EventLevel, Query(description="Nivel mínimo")] = EventLevel.INFO,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[LogEventResponse]:
    """Logger: eventos de la ejecución en orden (visibles mientras corre)."""
    return await service.get_logs(etl_run_id, level, limit)
