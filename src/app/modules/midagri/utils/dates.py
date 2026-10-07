"""Fechas de negocio en hora de Lima (el portal SISAP y los mercados publican por día peruano)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

LIMA = ZoneInfo("America/Lima")


def today_lima(now: datetime | None = None) -> date:
    """Fecha de hoy en Lima. En UTC ya es "mañana" desde las 19:00 de Lima (el legado usaba la hora local).

    Args:
        now: Momento a convertir (con zona horaria). Por defecto, ahora.
    """
    return (now or datetime.now(LIMA)).astimezone(LIMA).date()


def default_window(days: int, now: datetime | None = None) -> tuple[date, date]:
    """Ventana por defecto del ETL: de hace `days` días hasta hoy, en fechas de Lima (el legado usaba hoy-5..hoy)."""
    date_to = today_lima(now)
    return date_to - timedelta(days=days), date_to
