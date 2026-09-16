"""Temporary rows for a validated CMDB snapshot before atomic activation."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CmdbStagingCi(Base):
    __tablename__ = "cmdb_import_staging"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_run_id: Mapped[int] = mapped_column(ForeignKey("cmdb_import_runs.id"), index=True)
    hostname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cmdb_app: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cmdb_role: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cmdb_env: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cmdb_loc: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ven_installed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    wave: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    public_ip: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    distinguished_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ip_with_default_gw: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_gw: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    data_center: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    data_center_zone: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    service_provider: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cloud_instance_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    os: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    os_detail: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parent_application: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parent_sys_class_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    child_sys_class_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sys_created_on: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    u_last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    imported_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    extra_fields: Mapped[Optional[dict]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
