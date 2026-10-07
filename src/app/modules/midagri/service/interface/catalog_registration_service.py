"""Contrato del registro de faltantes: subida del Excel (D33, D34) y alta automática del ETL (D36)."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.modules.common.pagination.paginated import Paginated
from app.modules.midagri.dto.response.catalog_registration_response import (
    CatalogRegistrationResponse,
    CatalogRegistrationSummaryResponse,
)
from app.modules.midagri.dto.response.gap_report_response import GapItemResponse


class CatalogRegistrationService(ABC):
    """Valida cultivos y productos faltantes y los registra con los SP del app. Nunca activa ni modifica cultivos."""

    @abstractmethod
    async def register(
        self, file_name: str, content: bytes, *, dry_run: bool, requested_by: str | None
    ) -> CatalogRegistrationResponse:
        """Valida todas las filas y, si `dry_run` es False y todas son válidas, registra las nuevas.

        Si alguna fila es inválida no se registra ninguna. Cada alta va en su propia transacción; un fallo del
        SP en una fila no detiene las demás. La subida queda en `catalog_load` (también con `dry_run`).

        Raises:
            UnprocessableEntityException: Si el archivo no se puede leer, no tiene la hoja `Registro` o sus
                encabezados no son los del catálogo.
            ConflictException: Si el SP del catálogo reemplaza el código por un correlativo.
        """

    @abstractmethod
    async def register_gaps(
        self, items: Sequence[GapItemResponse], *, etl_run_id: int, dry_run: bool
    ) -> CatalogRegistrationResponse:
        """Alta automática (D36): registra los faltantes del reporte de una ejecución con las reglas de `register`.

        El llamador filtra antes los faltantes por mercado activo. Los ESC1 crean su cultivo antes que sus productos.
        Queda en `catalog_load` con `etl_run_id`.

        Raises:
            ConflictException: Si el SP del catálogo reemplaza el código por un correlativo.
        """

    @abstractmethod
    async def list_loads(self, page: int, size: int) -> Paginated[CatalogRegistrationSummaryResponse]:
        """Subidas, la más reciente primero."""

    @abstractmethod
    async def get_load(self, catalog_load_id: int) -> CatalogRegistrationResponse:
        """Subida con sus filas.

        Raises:
            NotFoundException: Si la subida no existe.
        """
