"""`dbo.IT_Multitabla`: cabeceras de la multi gestión (ajena, solo lectura)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.midagri.model.mssql.base import MssqlBase


class Multitabla(MssqlBase):
    """Multitabla de la multi gestión (p. ej. `BM_TCATCAT`, id 49)."""

    __tablename__ = "IT_Multitabla"

    multitabla_id: Mapped[int] = mapped_column("MultitablaId", Integer, primary_key=True, autoincrement=True)
    tabla: Mapped[str | None] = mapped_column("Tabla", String(20))
    nombre: Mapped[str | None] = mapped_column("Nombre", String(80))
    descripcion: Mapped[str | None] = mapped_column("Descripcion", String(150))
    activo: Mapped[bool] = mapped_column("Activo", Boolean)
    fecha_creacion: Mapped[datetime] = mapped_column("FechaCreacion", DateTime)
    usuario_creacion: Mapped[str | None] = mapped_column("UsuarioCreacion", String(40))
    fecha_modificacion: Mapped[datetime | None] = mapped_column("FechaModificacion", DateTime)
    usuario_modificacion: Mapped[str | None] = mapped_column("UsuarioModificacion", String(40))
