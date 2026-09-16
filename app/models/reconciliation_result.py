from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ReconciliationResult(Base):
    """
    Stores one row per field-level mismatch between an Illumio workload
    and the CMDB source of truth.

    status values:
        matched            - field agrees between Illumio and CMDB
        mismatch           - field exists in both but values differ
        missing_in_illumio - workload exists in CMDB but not in Illumio
        missing_in_cmdb    - workload exists in Illumio but not in CMDB
        label_missing      - workload matched but Illumio has no value for this label
        orphaned           - Illumio workload has no CMDB record at all

    resolution_action values:
        pending    - not yet actioned
        approved   - user approved, ready to push to PCE
        applied    - successfully written back to PCE via API
        skipped    - user decided not to change
        failed     - write-back to PCE failed
    """

    __tablename__ = "reconciliation_results"
    __table_args__ = (
        # Reconciliation browsing always scopes to a run first, then applies
        # outcome/review/field filters and orders by hostname.
        Index(
            "ix_reconciliation_results_run_filters_hostname",
            "run_id", "status", "resolution_action", "field_name", "hostname",
        ),
        # Covers the unfiltered browser path (the normal page/jump flow).
        Index("ix_reconciliation_results_run_hostname", "run_id", "hostname"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # --- Optional navigation links ---
    # New runs deliberately leave these null. Immutable hostname/value columns
    # are the historical record and must survive active snapshot replacement.
    illumio_workload_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("illumio_workloads.id"),
        nullable=True,
        index=True,
    )
    cmdb_ci_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cmdb_cis.id"),
        nullable=True,
        index=True,
    )

    # --- Identity ---
    hostname: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    illumio_href: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )

    # --- What field is being compared ---
    # Canonical keys: application, role, environment, location. Workload-level
    # outcomes use ``workload``.
    field_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )

    # --- The values being compared ---
    illumio_value: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    cmdb_value: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # --- Outcome ---
    status: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    )

    # --- Resolution ---
    resolution_action: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    # --- Audit ---
    run_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # --- Relationships ---
    workload = relationship("IllumioWorkload", foreign_keys=[illumio_workload_id])
    cmdb_ci = relationship("CmdbCi", foreign_keys=[cmdb_ci_id])
