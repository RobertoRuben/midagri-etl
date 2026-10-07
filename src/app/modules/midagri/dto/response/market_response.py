"""Mercados de `BM_Market`."""

from pydantic import BaseModel, ConfigDict


class MarketResponse(BaseModel):
    """Mercado SISAP. Se activa o desactiva en SQL Server (`BM_Market.active`)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    source: str
    active: bool
