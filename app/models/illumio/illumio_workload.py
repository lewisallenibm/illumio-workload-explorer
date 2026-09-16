from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Index, JSON
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.models.base import Base


class IllumioWorkload(Base):

    __tablename__ = "illumio_workloads"
    __table_args__ = (
        # Matches the active browser's exact online/enforcement filters plus
        # hostname ordering; contains search still intentionally uses a scan.
        Index("ix_illumio_workloads_online_enforcement_hostname", "online", "enforcement_mode", "hostname"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    illumio_href: Mapped[Optional[str]] = mapped_column(
        String(512),
        unique=True,
        nullable=True,
        index=True
    )

    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    hostname: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    online: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )

    connectivity_status: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    enforcement_mode: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )

    visibility_status: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    policy_sync_status: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    ransomware_exposure: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    protection_status: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    protection_coverage_score: Mapped[
        Optional[float]
    ] = mapped_column(
        Float,
        nullable=True
    )

    ven_version: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    os: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    os_release: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    uptime_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    location_text: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    heartbeat_last_received_at: Mapped[
        Optional[datetime]
    ] = mapped_column(
        DateTime,
        nullable=True
    )

    paired_at: Mapped[
        Optional[datetime]
    ] = mapped_column(
        DateTime,
        nullable=True
    )

    last_applied_policy_at: Mapped[
        Optional[datetime]
    ] = mapped_column(
        DateTime,
        nullable=True
    )

    first_seen_at: Mapped[
        Optional[datetime]
    ] = mapped_column(
        DateTime,
        nullable=True
    )

    last_seen_at: Mapped[
        Optional[datetime]
    ] = mapped_column(
        DateTime,
        nullable=True
    )

    last_synced_at: Mapped[
        Optional[datetime]
    ] = mapped_column(
        DateTime,
        nullable=True
    )

    raw_json: Mapped[Optional[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True
    )

    interfaces = relationship(
        "IllumioInterface",
        back_populates="workload",
        lazy="select",
    )

    labels = relationship(
        "IllumioWorkloadLabel",
        back_populates="workload",
        lazy="select",
    )
