"""Entorno de Alembic: solo PostgreSQL (D22).

Usa la metadata de `app.modules.common.model.Base`, en la que se registran los modelos de
`app.modules.midagri.model.pg`. Los modelos de SQL Server (`MssqlBase`) no se importan aquí,
así que un `--autogenerate` nunca propone tablas de `BDFARMEX`.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.modules.midagri.model.pg  # noqa: F401  (registra los modelos en Base.metadata)
from app.modules.common.db.session import pg_url
from app.modules.common.model import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL de las migraciones sin conectarse a la base (`alembic upgrade --sql`)."""
    context.configure(
        url=pg_url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Ejecuta las migraciones sobre una conexión síncrona entregada por `run_sync`."""
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Abre un engine asíncrono propio (sin pool) y corre las migraciones."""
    connectable = create_async_engine(pg_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Corre las migraciones contra la base configurada en `MIDAGRI_PG_*`."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
