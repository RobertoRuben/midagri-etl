"""`dbo.BM_Ubigeo`: departamentos, provincias y distritos (ajena, solo lectura)."""

import uuid as uuid_lib
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.midagri.model.mssql.base import MssqlBase


class Ubigeo(MssqlBase):
    """Ubigeo. Un departamento tiene `province` y `district` en `NULL`; una provincia, `district` en `NULL`."""

    __tablename__ = "BM_Ubigeo"

    uuid: Mapped[uuid_lib.UUID | None] = mapped_column(Uuid)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inei: Mapped[str | None] = mapped_column(String(10))
    reniec: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str | None] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    macroregion_inei: Mapped[str | None] = mapped_column(String(100))
    macroregion_minsa: Mapped[str | None] = mapped_column(String(100))
    iso_3166_2: Mapped[str | None] = mapped_column(String(10))
    fips: Mapped[str | None] = mapped_column(String(10))
    capital: Mapped[str | None] = mapped_column(String(100))
    area: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    population_density: Mapped[Decimal | None] = mapped_column("populationDensity", Numeric(10, 2))
    altitude: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(11, 8))
    state_density_index: Mapped[Decimal | None] = mapped_column("stateDensityIndex", Numeric(10, 2))
    food_vulnerability_index: Mapped[Decimal | None] = mapped_column("foodVulnerabilityIndex", Numeric(10, 2))
    idh: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pct_total_poverty: Mapped[Decimal | None] = mapped_column("pctTotalPoverty", Numeric(5, 2))
    pct_extreme_poverty: Mapped[Decimal | None] = mapped_column("pctExtremePoverty", Numeric(5, 2))
    id_parent: Mapped[int | None] = mapped_column("idParent", Integer)
    type: Mapped[str | None] = mapped_column(String(50))
    active: Mapped[bool | None] = mapped_column(Boolean)
    deleted: Mapped[bool | None] = mapped_column(Boolean)
    registration_date: Mapped[datetime | None] = mapped_column("registrationDate", DateTime)
    registered_by: Mapped[str | None] = mapped_column("registeredBy", String(20))
    edit_date: Mapped[datetime | None] = mapped_column("editDate", DateTime)
    edited_by: Mapped[str | None] = mapped_column("editedBy", String(20))
    deletion_date: Mapped[datetime | None] = mapped_column("deletionDate", DateTime)
    deleted_by: Mapped[str | None] = mapped_column("deletedBy", String(20))
