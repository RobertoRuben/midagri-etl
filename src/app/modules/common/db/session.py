"""Engines y fábricas de sesión asíncronas de las dos bases de datos (D21, D23).

- PostgreSQL (`asyncpg`): tablas propias de la API, gestionadas por Alembic.
- SQL Server (`aioodbc`): tablas de negocio de `BDFARMEX`, cuyo esquema se cambia con scripts SQL.

Una transacción nunca abarca las dos bases: cada repositorio recibe la sesión de la suya.
"""

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.modules.common.config import base_config

pg_url: URL = URL.create(
    drivername="postgresql+asyncpg",
    host=base_config.pg_host,
    port=base_config.pg_port,
    username=base_config.pg_username,
    password=base_config.pg_password.get_secret_value(),
    database=base_config.pg_database,
)

mssql_url: URL = URL.create(
    drivername="mssql+aioodbc",
    host=base_config.mssql_host,
    port=base_config.mssql_port,
    username=base_config.mssql_username,
    password=base_config.mssql_password.get_secret_value(),
    database=base_config.mssql_database,
    query={"driver": base_config.mssql_driver},
)

pg_engine: AsyncEngine = create_async_engine(
    pg_url,
    echo=base_config.database_debug,
    pool_pre_ping=True,
    pool_size=base_config.pg_pool_size,
    max_overflow=base_config.pg_max_overflow,
    pool_recycle=base_config.database_pool_recycle,
)

mssql_engine: AsyncEngine = create_async_engine(
    mssql_url,
    echo=base_config.database_debug,
    pool_pre_ping=True,
    pool_size=base_config.mssql_pool_size,
    max_overflow=base_config.mssql_max_overflow,
    pool_recycle=base_config.database_pool_recycle,
    fast_executemany=True,
)

PgSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=pg_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

MssqlSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=mssql_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def dispose_engines() -> None:
    """Cierra los pools de conexiones de ambas bases. Se llama al apagar la aplicación."""
    await pg_engine.dispose()
    await mssql_engine.dispose()
