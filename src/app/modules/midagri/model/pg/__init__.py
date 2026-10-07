"""Modelos de PostgreSQL: tablas propias de la API, gestionadas por Alembic.

Cada modelo nuevo se importa aquí para que `alembic/env.py` lo registre en `Base.metadata`.
"""

from app.modules.midagri.model.pg.catalog_load import CatalogLoad, CatalogLoadItem
from app.modules.midagri.model.pg.etl_run import EtlRun
from app.modules.midagri.model.pg.etl_run_event import EtlRunEvent
from app.modules.midagri.model.pg.gap_report import GapReport
from app.modules.midagri.model.pg.mail_log import MailLog
from app.modules.midagri.model.pg.mail_recipient import MailRecipient
from app.modules.midagri.model.pg.price_load import PriceLoad

__all__: list[str] = [
    "CatalogLoad",
    "CatalogLoadItem",
    "EtlRun",
    "EtlRunEvent",
    "GapReport",
    "MailLog",
    "MailRecipient",
    "PriceLoad",
]
