from datetime import datetime

from sqlalchemy import BigInteger, DateTime, MetaData, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_N_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class Base(AsyncAttrs, DeclarativeBase):
    """Clase base de los modelos de PostgreSQL: `id` BIGINT identity y columnas de auditoría `timestamptz`.

    La convención de nombres asigna un nombre determinista a cada restricción (constraints),
    permitiendo que las migraciones de reversión de Alembic puedan referenciarlas.
    Cualquier clave foránea que apunte a `id` debe declararse también como `BigInteger`.
    """

    __abstract__ = True
    metadata = metadata

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
