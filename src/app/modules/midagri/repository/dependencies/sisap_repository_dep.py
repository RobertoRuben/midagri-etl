"""Dependencia FastAPI del repositorio del portal SISAP (un cliente HTTP por solicitud)."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends

from app.modules.common.config import base_config
from app.modules.midagri.repository.impl.sisap_repository_impl import SisapRepositoryImpl, build_sisap_client
from app.modules.midagri.repository.interface.sisap_repository import SisapRepository


async def get_sisap_repository() -> AsyncGenerator[SisapRepository]:
    """Abre el cliente HTTP del portal y lo cierra al terminar la solicitud."""
    async with build_sisap_client(base_config.sisap_base_url, base_config.sisap_timeout_seconds) as client:
        yield SisapRepositoryImpl(
            client,
            concurrency=base_config.sisap_concurrency,
            retries=base_config.sisap_retries,
        )


SisapRepositoryDep = Annotated[SisapRepository, Depends(get_sisap_repository)]
