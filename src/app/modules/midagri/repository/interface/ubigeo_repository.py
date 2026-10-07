"""Contrato de resolución de regiones SISAP contra `BM_Ubigeo`."""

from typing import Protocol

import polars as pl

from app.modules.common.repository.interface.generic_repository import GenericRepository
from app.modules.midagri.model.mssql import Ubigeo


class UbigeoRepository(GenericRepository[Ubigeo], Protocol):
    """Ubigeos. Solo lectura."""

    async def region_lookup(self) -> pl.DataFrame:
        """Índice `key → id` para cruzar regiones SISAP en Polars (ver `build_region_lookup`)."""
        ...

    async def resolve(self, region_name: str) -> int | None:
        """`idUbigeo` de una región SISAP (p. ej. `"Lima Metropolitana"` → distrito Lima), o `None`."""
        ...
