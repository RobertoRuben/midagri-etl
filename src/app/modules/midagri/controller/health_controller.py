"""`/health`: estado del servicio, sin autenticación."""

from fastapi import APIRouter

from app.modules.common.types.openapi import TagMetadata
from app.modules.midagri.dto.response.health_response import HealthResponse
from app.modules.midagri.service.dependencies.etl_run_deps import HealthServiceDep

TAG: TagMetadata = {"name": "health", "description": "Estado del servicio, SQL Server, PostgreSQL y el portal SISAP."}

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health(service: HealthServiceDep) -> HealthResponse:
    """`ok` si todo responde; `degraded` (también con 200) indicando qué falla."""
    return await service.check()
