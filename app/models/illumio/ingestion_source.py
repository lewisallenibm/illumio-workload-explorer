from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class IngestionSource(Base):
    """Safe, compact provenance for a current-domain Illumio sync/import."""

    __tablename__ = "ingestion_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_run_id: Mapped[int] = mapped_column(ForeignKey("sync_runs.id"), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    sync_run = relationship("SyncRun")
