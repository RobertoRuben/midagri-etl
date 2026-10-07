"""`dbo.IT_Multivalor`: valores de la multi gestión (ajena, solo lectura en la fase 1).

Los cultivos son las filas con `Tabla='BM_TCATCAT'` y `systemCodeCluster='CROP'`; `Valor` es el
código de 4 dígitos que usa `BM_Catalog.category`.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.midagri.model.mssql.base import MssqlBase


class Multivalor(MssqlBase):
    """Valor de una multitabla (p. ej. un cultivo)."""

    __tablename__ = "IT_Multivalor"

    multivalor_id: Mapped[int] = mapped_column("MultivalorId", Integer, primary_key=True, autoincrement=True)
    multitabla_id: Mapped[int] = mapped_column("MultitablaId", Integer)
    tabla: Mapped[str | None] = mapped_column("Tabla", String(80))
    valor: Mapped[str | None] = mapped_column("Valor", String(80))
    nombre: Mapped[str | None] = mapped_column("Nombre", String(80))
    valor1: Mapped[str | None] = mapped_column("Valor1", String(50))
    valor2: Mapped[str | None] = mapped_column("Valor2", String(50))
    valor3: Mapped[str | None] = mapped_column("Valor3", String(50))
    valor4: Mapped[str | None] = mapped_column("Valor4", String(50))
    activo: Mapped[bool] = mapped_column("Activo", Boolean)
    fecha_creacion: Mapped[datetime] = mapped_column("FechaCreacion", DateTime)
    usuario_creacion: Mapped[str | None] = mapped_column("UsuarioCreacion", String(40))
    fecha_modificacion: Mapped[datetime | None] = mapped_column("FechaModificacion", DateTime)
    usuario_modificacion: Mapped[str | None] = mapped_column("UsuarioModificacion", String(40))
    id_organization: Mapped[int | None] = mapped_column("idOrganization", Integer)
    system_code: Mapped[str | None] = mapped_column("systemCode", String(50))
    system_code_cluster: Mapped[str | None] = mapped_column("systemCodeCluster", String(50))
