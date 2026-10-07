"""Estado del servicio y sus dependencias."""

from typing import Literal

from pydantic import BaseModel

CheckStatus = Literal["ok", "error"]


class HealthResponse(BaseModel):
    """`ok` si SQL Server, PostgreSQL y el portal SISAP responden; si no, `degraded` e indica cuál falla."""

    status: Literal["ok", "degraded"]
    mssql: CheckStatus
    postgres: CheckStatus
    sisap: CheckStatus
    details: dict[str, str] = {}
