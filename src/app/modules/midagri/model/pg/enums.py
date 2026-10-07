"""Estados y tipos de las tablas de PostgreSQL. Se guardan como texto con `CHECK` (`native_enum=False`)."""

from enum import StrEnum

from sqlalchemy import Enum


class RunStatus(StrEnum):
    """Estado de una ejecución del ETL."""

    QUEUED = "queued"
    RUNNING = "running"
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


ACTIVE_RUN_STATUSES: tuple[RunStatus, ...] = (RunStatus.QUEUED, RunStatus.RUNNING)
"""Estados de una ejecución en curso (a lo sumo una a la vez, por `uq_etl_run_active`)."""


class RunTrigger(StrEnum):
    """Quién disparó la ejecución."""

    CRON = "cron"
    MANUAL = "manual"


class EventLevel(StrEnum):
    """Nivel de un evento del logger."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LoadStatus(StrEnum):
    """Resultado de la carga de precios de un mercado."""

    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class MailKind(StrEnum):
    """Correo de inicio, de fin o de incidencias (D37) de una ejecución."""

    START = "start"
    END = "end"
    ERROR = "error"


class MailStatus(StrEnum):
    """Resultado del envío de un correo."""

    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class CatalogLoadStatus(StrEnum):
    """Resultado de una subida de la hoja `Registro` (D33)."""

    VALIDATED = "validated"
    """`dry_run`: todas las filas válidas, nada escrito."""
    INVALID = "invalid"
    """Alguna fila inválida: no se registró ninguna."""
    APPLIED = "applied"
    PARTIAL = "partial"
    """Se registraron algunas; otras fallaron en el SP."""
    FAILED = "failed"


class RegistrationOutcome(StrEnum):
    """Resultado de una fila de la hoja `Registro`."""

    PLANNED = "planned"
    CREATED = "created"
    SKIPPED_EXISTS = "skipped_exists"
    INVALID = "invalid"
    ERROR = "error"


def text_enum[E: StrEnum](enum: type[E], name: str) -> Enum:
    """Columna de enum guardada como texto (sus valores, no sus nombres) con `CHECK`."""
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
