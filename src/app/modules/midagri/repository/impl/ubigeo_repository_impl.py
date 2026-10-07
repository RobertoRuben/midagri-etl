"""Resolución de regiones SISAP contra `BM_Ubigeo` en SQL Server."""

import logging

import polars as pl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.repository.impl.generic_repository_impl import GenericRepositoryImpl
from app.modules.midagri.model.mssql import Ubigeo
from app.modules.midagri.repository.interface.ubigeo_repository import UbigeoRepository
from app.modules.midagri.utils.catalog_lookup import build_region_lookup
from app.modules.midagri.utils.text import norm_region

logger = logging.getLogger(__name__)

UBIGEO_FRAME_SCHEMA: dict[str, type[pl.DataType]] = {
    "id": pl.Int64,
    "department": pl.String,
    "province": pl.String,
    "district": pl.String,
}


class UbigeoRepositoryImpl(GenericRepositoryImpl[Ubigeo], UbigeoRepository):
    """Ubigeos. El índice de regiones se calcula una vez por instancia (una solicitud o una ejecución)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Ubigeo, session)
        self._lookup: pl.DataFrame | None = None

    async def region_lookup(self) -> pl.DataFrame:
        if self._lookup is None:
            stmt = select(Ubigeo.id, Ubigeo.department, Ubigeo.province, Ubigeo.district)
            rows = (await self.session.execute(stmt)).mappings().all()
            frame = pl.DataFrame([dict(row) for row in rows], schema=UBIGEO_FRAME_SCHEMA)
            self._lookup, ambiguous = build_region_lookup(frame)
            if ambiguous.height:
                logger.info(
                    "%s nombres de ubigeo se repiten en su nivel; se usa el menor id (p. ej. %s)",
                    ambiguous.height,
                    ambiguous.head(3).to_dicts(),
                )
        return self._lookup

    async def resolve(self, region_name: str) -> int | None:
        lookup = await self.region_lookup()
        match = lookup.filter(pl.col("key") == norm_region(region_name))
        return match.item(0, "id") if match.height else None
