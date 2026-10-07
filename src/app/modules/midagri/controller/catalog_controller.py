"""`/catalog/gaps`: último reporte de faltantes (JSON y Excel) y recálculo a pedido (D27)."""

from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.modules.common.exception import ConflictException
from app.modules.common.security.static_api_key import API_KEY_RESPONSES, require_api_key
from app.modules.common.types.api_responses import ResponsesDict, problem_response
from app.modules.common.types.openapi import TagMetadata
from app.modules.midagri.dto.response.gap_report_response import GapReportResponse
from app.modules.midagri.service.dependencies.etl_run_deps import EtlRunnerDep, GapReportServiceDep

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

TAG: TagMetadata = {
    "name": "catalog",
    "description": "Faltantes del catálogo (ESC1/ESC2). Se calculan en cada ejecución del ETL; aquí se lee el último.",
}

router = APIRouter(
    prefix="/catalog/gaps",
    tags=["catalog"],
    dependencies=[Depends(require_api_key)],
    responses=API_KEY_RESPONSES,
)

NOT_FOUND: ResponsesDict = {status.HTTP_404_NOT_FOUND: problem_response("Todavía no hay reportes de faltantes.")}
EXCEL_RESPONSES: ResponsesDict = {
    status.HTTP_200_OK: {"content": {XLSX: {}}, "description": "Excel listo para cargar."},
    **NOT_FOUND,
}


class GapRefreshResponse(BaseModel):
    """Recálculo aceptado: corre en segundo plano y queda como el último reporte."""

    status: Literal["started"] = "started"


@router.get("", responses=NOT_FOUND)
async def latest_report(service: GapReportServiceDep) -> GapReportResponse:
    """Último reporte de faltantes, al instante."""
    return await service.latest()


@router.get(
    "/excel",
    response_class=Response,
    responses=EXCEL_RESPONSES,
)
async def latest_excel(service: GapReportServiceDep) -> Response:
    """Excel del último reporte: productos que no se cargaron por no estar en el catálogo, con sus códigos."""
    excel = await service.latest_excel()
    return Response(
        content=excel.content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{excel.filename}"'},
    )


@router.post(
    "/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    responses={status.HTTP_409_CONFLICT: problem_response("Ya hay un recálculo en curso.")},
)
async def refresh(runner: EtlRunnerDep) -> GapRefreshResponse:
    """Recalcula los faltantes consultando el portal en vivo (tarda minutos). Queda como el último reporte."""
    if not runner.start_gap_refresh():
        raise ConflictException("Ya hay un recálculo de faltantes en curso.")
    return GapRefreshResponse()
