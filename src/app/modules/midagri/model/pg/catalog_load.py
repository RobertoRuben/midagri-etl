"""`catalog_load` y `catalog_load_item`: subidas de las hojas `Cultivos` y `Registro` y el resultado de cada fila."""

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text, literal_column
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.common.model import Base
from app.modules.midagri.model.pg.enums import CatalogLoadStatus, RegistrationOutcome, text_enum


class CatalogLoad(Base):
    """Una subida del Excel a `POST /catalog/registrations` o un alta automática del ETL (D36), con `dry_run` o sin él."""

    __tablename__ = "catalog_load"
    __table_args__ = (Index("ix_catalog_load_created_at", literal_column("created_at DESC")),)

    file_name: Mapped[str] = mapped_column(String(200))
    file_sha256: Mapped[str] = mapped_column(String(64))
    requested_by: Mapped[str | None] = mapped_column(String(100))
    dry_run: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[CatalogLoadStatus] = mapped_column(text_enum(CatalogLoadStatus, "catalog_load_status"))
    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    planned: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    skipped: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    invalid: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    etl_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("etl_run.id", ondelete="SET NULL"))
    """Ejecución que hizo el alta automática (D36). `None` en las subidas del Excel."""


class CatalogLoadItem(Base):
    """Una fila de la hoja `Cultivos` o `Registro` y lo que pasó con ella."""

    __tablename__ = "catalog_load_item"
    __table_args__ = (Index("ix_catalog_load_item_catalog_load_id_row_number", "catalog_load_id", "row_number"),)

    catalog_load_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("catalog_load.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10), default="product", server_default="product")
    """`crop` (hoja `Cultivos`, D34) o `product` (hoja `Registro`)."""
    row_number: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    crop_code: Mapped[str] = mapped_column(String(10))
    outcome: Mapped[RegistrationOutcome] = mapped_column(text_enum(RegistrationOutcome, "registration_outcome"))
    detail: Mapped[str | None] = mapped_column(Text)
