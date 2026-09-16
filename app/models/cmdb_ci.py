from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CmdbCi(Base):
    """
    Stores per-machine records imported from the UPS ServiceNow CMDB.

    Supports two import formats:
      1. Raw cmdb_rel_ci export  (parent/child relationship table)
      2. Processed Inventory Lookup sheet (one row per machine, labels flattened)

    The four label columns (cmdb_app, cmdb_role, cmdb_env, cmdb_loc) are the
    source of truth used during reconciliation against Illumio.
    All other columns are stored for reference / visibility.
    """

    __tablename__ = "cmdb_cis"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # --- Primary join key against illumio_workloads.hostname ---
    hostname: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )

    # --- The four labels Ben cares about (source of truth) ---
    cmdb_app: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    cmdb_role: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    cmdb_env: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    cmdb_loc: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )

    # --- Additional CMDB fields (visible in UI, not used for reconciliation) ---
    ven_installed: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )
    region: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    wave: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Network / identity fields ---
    public_ip: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    distinguished_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ip_with_default_gw: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_gw: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    data_center: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    data_center_zone: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    service_provider: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cloud_instance_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --- OS ---
    os: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    os_detail: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --- CMDB relationship fields (from raw cmdb_rel_ci format) ---
    parent_application: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    parent_sys_class_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    child_sys_class_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # --- Timestamps ---
    sys_created_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    u_last_seen: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    imported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # --- Catch-all for any columns not explicitly modelled ---
    extra_fields: Mapped[Optional[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
