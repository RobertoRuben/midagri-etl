"""`/markets`: mercados de `BM_Market`."""

from fastapi import APIRouter, Depends

from app.modules.common.security.static_api_key import API_KEY_RESPONSES, require_api_key
from app.modules.common.types.openapi import TagMetadata
from app.modules.midagri.dto.response.market_response import MarketResponse
from app.modules.midagri.service.dependencies.etl_run_deps import MarketServiceDep

TAG: TagMetadata = {
    "name": "markets",
    "description": "Mercados SISAP. Se activan por fases con `BM_Market.active` en SQL Server (D28).",
}

router = APIRouter(
    prefix="/markets",
    tags=["markets"],
    dependencies=[Depends(require_api_key)],
    responses=API_KEY_RESPONSES,
)


@router.get("")
async def list_markets(service: MarketServiceDep) -> list[MarketResponse]:
    """Todos los mercados, activos primero."""
    return await service.list_all()
