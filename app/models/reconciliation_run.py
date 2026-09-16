from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class ReconciliationRun(Base):
    """Immutable provenance and aggregate outcomes for one comparison."""

    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cmdb_import_run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    illumio_sync_run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    matched_workloads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label_mismatches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label_missing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_expected_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_in_illumio: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orphaned_in_illumio: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ambiguous_matches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actionable_results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
