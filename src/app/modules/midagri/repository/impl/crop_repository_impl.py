"""Cultivos en `IT_Multivalor` (SQL Server): lecturas y alta con el SP del app (D34)."""

from xml.sax.saxutils import quoteattr

import polars as pl
from sqlalchemy import Select, literal, select, text, true
from sqlalchemy.exc import ResourceClosedError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.repository.impl.generic_repository_impl import GenericRepositoryImpl
from app.modules.midagri.model.mssql import Multivalor
from app.modules.midagri.repository.interface.catalog_repository import SpResult
from app.modules.midagri.repository.interface.crop_repository import CropRepository
from app.modules.midagri.utils.catalog_constants import CROP_CLUSTER, CROP_TABLE, ORGANIZATION_ID

CROP_FRAME_SCHEMA: dict[str, type[pl.DataType]] = {"code": pl.String, "name": pl.String, "active": pl.Boolean}
CROP_MULTITABLA_ID = 49
"""`IT_Multitabla.MultitablaId` de `BM_TCATCAT`."""
CROP_VALOR1 = "MIDAGRI"

_CREATE = text(
    "SET NOCOUNT ON; EXEC dbo.uspIT_GuardarActualizarMultivalores @xmlMultivalores=:xml, "
    "@idMultitabla=:multitabla, @tablaMultitabla=:tabla, @usuario=:user, @idOrganization=:organization;"
)


class CropRepositoryImpl(GenericRepositoryImpl[Multivalor], CropRepository):
    """Cultivos de MIDAGRI: `Tabla='BM_TCATCAT'`, `systemCodeCluster='CROP'`, `idOrganization=1`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Multivalor, session)

    @staticmethod
    def _crops() -> Select[tuple[Multivalor]]:
        return (
            select(Multivalor)
            .where(
                Multivalor.tabla == CROP_TABLE,
                Multivalor.system_code_cluster == CROP_CLUSTER,
                Multivalor.id_organization == ORGANIZATION_ID,
            )
            .order_by(Multivalor.valor, Multivalor.multivalor_id)
        )

    async def list_active(self) -> list[Multivalor]:
        return list(await self.session.scalars(self._crops().where(Multivalor.activo == true())))

    async def list_all(self) -> list[Multivalor]:
        return list(await self.session.scalars(self._crops()))

    async def find_by_code(self, code: str) -> Multivalor | None:
        return (await self.session.scalars(self._crops().where(Multivalor.valor == code).limit(1))).first()

    async def frame_all(self) -> pl.DataFrame:
        stmt = (
            select(
                Multivalor.valor.label("code"),
                Multivalor.nombre.label("name"),
                Multivalor.activo.label("active"),
            )
            .where(
                Multivalor.tabla == CROP_TABLE,
                Multivalor.system_code_cluster == CROP_CLUSTER,
                Multivalor.id_organization == ORGANIZATION_ID,
            )
            .order_by(Multivalor.valor)
        )
        rows = (await self.session.execute(stmt)).mappings().all()
        return pl.DataFrame([dict(row) for row in rows], schema=CROP_FRAME_SCHEMA)

    async def exists_any(self, code: str) -> bool:
        stmt = (
            select(literal(1))
            .select_from(Multivalor)
            .where(
                Multivalor.tabla == CROP_TABLE, Multivalor.valor == code, Multivalor.id_organization == ORGANIZATION_ID
            )
            .limit(1)
        )
        return await self.session.scalar(stmt) is not None

    async def create_via_sp(self, *, code: str, name: str, user: str) -> SpResult:
        item = (
            f'<item MultivalorId="0" Valor={quoteattr(code)} Nombre={quoteattr(name)} '
            f"Valor1={quoteattr(CROP_VALOR1)} SystemCodeCluster={quoteattr(CROP_CLUSTER)}/>"
        )
        params = {
            "xml": f"<root>{item}</root>",
            "multitabla": CROP_MULTITABLA_ID,
            "tabla": CROP_TABLE,
            "user": user,
            "organization": ORGANIZATION_ID,
        }
        result = await self.session.execute(_CREATE, params)
        try:
            row = result.mappings().first()
        except ResourceClosedError:  # el SP no devolvió filas
            row = None
        values = {key.lower(): value for key, value in (row or {}).items()}
        open_transactions = await self.session.scalar(text("SELECT @@TRANCOUNT"))
        return SpResult(
            ok=str(values.get("status", "")).strip() in {"1", "True"},
            message=str(values.get("msg") or ""),
            transaction_open=bool(open_transactions),
        )
