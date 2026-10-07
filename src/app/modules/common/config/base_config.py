"""Configuración del proceso, leída desde variables de entorno `MIDAGRI_*` y el archivo `.env`."""

from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class BaseConfig(BaseSettings):
    """Configuración global de la aplicación.

    Los ajustes obligatorios no tienen valor por defecto: si falta alguno o está vacío,
    instanciar la clase (y por ende importar `app.modules.common.config`) genera una
    excepción `ValidationError` indicando el campo correspondiente. Solo los parámetros
    con un valor razonable poseen un valor predeterminado.

    Las variables sin prefijo del `.env` (`SQLSERVER_*`, `SISAP_*`) son del script legado
    y se ignoran aquí.
    """

    model_config = SettingsConfigDict(
        env_prefix="MIDAGRI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["dev", "qas", "prd"] = Field(default="dev")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    api_public_url: str = Field(default="http://localhost:8000")
    """URL con la que se llega a la API desde afuera (enlaces en los correos)."""

    # Autenticación del MVP: una sola X-API-Key (D24).
    api_key: SecretStr = Field(min_length=32)

    # SQL Server: tablas de negocio (BDFARMEX; en QAS, BDFarmex_Agri).
    mssql_host: str = Field(min_length=1)
    mssql_port: int = Field(default=1433)
    mssql_database: str = Field(min_length=1)
    mssql_username: str = Field(min_length=1)
    mssql_password: SecretStr = Field(min_length=1)
    mssql_driver: str = Field(default="ODBC Driver 17 for SQL Server")
    mssql_pool_size: int = Field(default=5, ge=1)
    mssql_max_overflow: int = Field(default=5, ge=0)

    # PostgreSQL: tablas propias de la API (D21).
    pg_host: str = Field(min_length=1)
    pg_port: int = Field(default=5432)
    pg_database: str = Field(min_length=1)
    pg_username: str = Field(min_length=1)
    pg_password: SecretStr = Field(min_length=1)
    pg_pool_size: int = Field(default=5, ge=1)
    pg_max_overflow: int = Field(default=10, ge=0)

    database_debug: bool = Field(default=False)
    database_pool_recycle: int = Field(default=3600, ge=60)

    # Portal SISAP.
    sisap_base_url: str = Field(default="http://sistemas.midagri.gob.pe/sisap/portal2")
    sisap_concurrency: int = Field(default=4, ge=1, le=16)
    sisap_timeout_seconds: int = Field(default=120, ge=1)
    sisap_retries: int = Field(default=3, ge=0)

    # ETL.
    etl_default_window_days: int = Field(default=5, ge=1)
    etl_excluded_markets: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["15010106"])
    catalog_auto_register: bool = Field(default=False)
    """Al final de cada ejecución, registra los faltantes en el catálogo con los SP del app (D36)."""

    # Correo: Gmail por SMTP (D37, por defecto) o Microsoft 365 vía Graph (D35).
    # Los destinatarios viven en `mail_recipient` (D25).
    mail_provider: Literal["gmail", "graph"] = Field(default="gmail")
    mail_smtp_host: str = Field(default="smtp.gmail.com")
    mail_smtp_port: int = Field(default=587)
    mail_username: str | None = Field(default=None)
    """Cuenta de Gmail que envía (autenticación SMTP)."""
    mail_password: SecretStr | None = Field(default=None)
    """Contraseña de aplicación de Gmail (16 caracteres; los espacios se ignoran)."""
    mail_tenant_id: str | None = Field(default=None)
    mail_client_id: str | None = Field(default=None)
    mail_client_secret: SecretStr | None = Field(default=None)
    mail_from: str | None = Field(default=None)
    mail_enabled: bool = Field(default=False)

    # Usado por `common/types/upload_types.py`.
    max_photo_bytes: int = Field(default=5 * 1024 * 1024, ge=1)

    @field_validator("etl_excluded_markets", mode="before")
    @classmethod
    def _split_markets(cls, value: object) -> object:
        """Acepta la lista como texto separado por comas (`15010106,15011503`)."""
        if isinstance(value, str):
            return [code.strip() for code in value.split(",") if code.strip()]
        return value

    @model_validator(mode="after")
    def _require_mail_when_enabled(self) -> Self:
        """Exige las credenciales del proveedor elegido solo si el envío de correos está activo.

        Con Gmail, el remitente por defecto es la misma cuenta (`mail_username`).
        """
        if self.mail_provider == "gmail" and self.mail_from is None:
            self.mail_from = self.mail_username
        if not self.mail_enabled:
            return self
        required = (
            ("mail_username", "mail_password")
            if self.mail_provider == "gmail"
            else ("mail_tenant_id", "mail_client_id", "mail_client_secret", "mail_from")
        )
        missing = [name for name in required if getattr(self, name) is None or "<pendiente" in str(getattr(self, name))]
        if missing:
            raise ValueError(
                f"MIDAGRI_MAIL_ENABLED=true con MIDAGRI_MAIL_PROVIDER={self.mail_provider} exige: {', '.join(missing)}"
            )
        return self


base_config = BaseConfig()
