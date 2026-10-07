from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import os

# Cargar env SIEMPRE desde la raíz del proyecto Midagri
BASE_DIR = Path(__file__).resolve().parents[2]   # /system/core → /system → /Midagri
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE, override=True)

@dataclass
class Settings:
    sql_server: str   = os.getenv("SQLSERVER_SERVER", "").strip()
    sql_database: str = os.getenv("SQLSERVER_DATABASE", "").strip()
    sql_user: str     = os.getenv("SQLSERVER_UID", "").strip()
    sql_pwd: str      = os.getenv("SQLSERVER_PWD", "").strip()

    fecha: str        = os.getenv("SISAP_FECHA", "").strip()
    desde: str        = os.getenv("SISAP_DESDE", "").strip()
    hasta: str        = os.getenv("SISAP_HASTA", "").strip()

    batch_size: int   = int(os.getenv("SISAP_BATCH_SIZE", "20"))
    price_type: str   = os.getenv("PRICE_TYPE", "Mayorista")
    periodicidad: str = os.getenv("SISAP_PERIODICIDAD", "intervalo")
    sisap_mode: str   = os.getenv("SISAP_MODE", "mayorista").strip().lower()

SETTINGS = Settings()
