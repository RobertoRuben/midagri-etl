"""Dependencias FastAPI que entregan una sesión por solicitud para cada base de datos."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.db.session import MssqlSessionLocal, PgSessionLocal


async def get_pg_session() -> AsyncGenerator[AsyncSession]:
    """Sesión de PostgreSQL (tablas propias de la API)."""
    async with PgSessionLocal() as session:
        yield session


async def get_mssql_session() -> AsyncGenerator[AsyncSession]:
    """Sesión de SQL Server (tablas de negocio de BDFARMEX)."""
    async with MssqlSessionLocal() as session:
        yield session


PgSessionDep = Annotated[AsyncSession, Depends(get_pg_session)]
MssqlSessionDep = Annotated[AsyncSession, Depends(get_mssql_session)]
