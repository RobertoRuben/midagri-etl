"""Contrato del catálogo de productos de mercado (`BM_Catalog`, `type='0001'`)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import polars as pl

from app.modules.common.repository.interface.generic_repository import GenericRepository
from app.modules.midagri.model.mssql import Catalog


@dataclass(frozen=True, slots=True)
class SpResult:
    """Lo que devuelve `uspBM_SaveUpdateCatalogo` (`STATUS`, `MSG`) y si la transacción sigue abierta."""

    ok: bool
    message: str
    transaction_open: bool


class CatalogRepository(GenericRepository[Catalog], Protocol):
    """Productos de mercado de MIDAGRI. Lecturas, y altas solo con el SP del app (D33).

    "Activo" significa `active=1` y `deleted=0`.
    """

    async def create_via_sp(self, *, code: str, name: str, crop_code: str, user: str) -> SpResult:
        """Da de alta un producto con `EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, …` en la transacción de la sesión.

        Mismos valores que usa el app: `type='0001'`, `process='-'`, `unitOfMeasure='KG'`, `idOrganization=1`,
        `active=1`; el resto en `NULL`. No comprueba duplicados (el SP tampoco): el llamador lo hace antes.
        """
        ...

    async def sp_uses_correlative(self) -> bool:
        """Indica si `uspBM_SaveUpdateCatalogo` reemplaza `@code` por un correlativo (lee `BM_TCATTY`).

        Esa versión existe en otro sistema del servidor de QAS; si llega a esta base, el código SISAP se perdería.
        """
        ...

    async def map_active_by_code(self, codes: Sequence[str]) -> dict[str, int]:
        """Resuelve códigos SISAP a `idCatalog` de productos activos.

        Si un código está repetido, devuelve el menor `id` y registra un warning. Los códigos que no
        existen o están inactivos no aparecen en el resultado.
        """
        ...

    async def exists_code(self, code: str) -> bool:
        """Indica si el código existe en el catálogo de mercado, activo o no (evita duplicar en la fase 2)."""
        ...

    async def find_by_codes(self, codes: Sequence[str]) -> list[Catalog]:
        """Productos de mercado con esos códigos, activos o no, ordenados por código e id."""
        ...

    async def frame_active(self) -> pl.DataFrame:
        """Productos activos como DataFrame: `id`, `code`, `name`, `category`."""
        ...
