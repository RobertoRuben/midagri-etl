"""Contrato de cultivos (`IT_Multivalor`, `Tabla='BM_TCATCAT'`, `systemCodeCluster='CROP'`)."""

from typing import Protocol

import polars as pl

from app.modules.common.repository.interface.generic_repository import GenericRepository
from app.modules.midagri.model.mssql import Multivalor
from app.modules.midagri.repository.interface.catalog_repository import SpResult


class CropRepository(GenericRepository[Multivalor], Protocol):
    """Cultivos de la multi gestión de MIDAGRI (`idOrganization=1`).

    Solo crea cultivos nuevos con el SP del app (D34); nunca activa, desactiva ni modifica uno existente (D6).
    """

    async def list_active(self) -> list[Multivalor]:
        """Cultivos activos (`Activo=1`), ordenados por código."""
        ...

    async def list_all(self) -> list[Multivalor]:
        """Cultivos activos e inactivos, ordenados por código. Para distinguir ESC1 de un cultivo inactivo."""
        ...

    async def find_by_code(self, code: str) -> Multivalor | None:
        """Cultivo por su código de 4 dígitos, sin filtrar por `Activo`."""
        ...

    async def frame_all(self) -> pl.DataFrame:
        """Cultivos activos e inactivos como DataFrame: `code`, `name`, `active`."""
        ...

    async def exists_any(self, code: str) -> bool:
        """Indica si hay alguna fila de `BM_TCATCAT` con ese código (cualquier estado o cluster), para no duplicar."""
        ...

    async def create_via_sp(self, *, code: str, name: str, user: str) -> SpResult:
        """Crea un cultivo activo con `uspIT_GuardarActualizarMultivalores` en la transacción de la sesión.

        Mismos valores que el app: `MultitablaId=49`, `Tabla='BM_TCATCAT'`, `Valor1='MIDAGRI'`,
        `SystemCodeCluster='CROP'`, `idOrganization=1`. No comprueba duplicados: el llamador lo hace antes.
        """
        ...
