"""Base declarativa de los modelos de SQL Server (`BDFARMEX`).

A diferencia de `app.modules.common.model.Base` (PostgreSQL), no impone columnas: las tablas de negocio
ya existen y usan la convención de la BD (`id INT IDENTITY`, `registrationDate`, `registeredBy`).
Alembic no gestiona esta metadata (D22); los cambios de esquema van en los scripts de `sql/`.
"""

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

metadata = MetaData(
    schema="dbo",
    naming_convention={
        "pk": "PK_%(table_name)s",
        "fk": "FK_%(table_name)s_%(column_0_name)s",
        "uq": "UQ_%(table_name)s_%(column_0_name)s",
        "ix": "IX_%(table_name)s_%(column_0_name)s",
    },
)


class MssqlBase(AsyncAttrs, DeclarativeBase):
    """Clase base de los modelos de SQL Server, con esquema `dbo` y la convención de nombres de la BD."""

    __abstract__ = True
    metadata = metadata
