"""Persistent, auditable configuration for scheduled pilot automations.

These rows deliberately contain configuration and execution history only.
SMTP and Box credentials are read from runtime environment variables, never
stored in PostgreSQL or displayed by the web UI.
"""

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class Automation(Base):
    """A scheduled system activity, independent from who receives its output."""

    __tablename__ = "automations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # DAILY or WEEKLY. The worker uses this as the default for subscriptions
    # that elect to inherit the task cadence.
    schedule_type: Mapped[str] = mapped_column(String(16), nullable=False, default="WEEKLY")
    weekday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_time_utc: Mapped[str] = mapped_column(String(5), nullable=False, default="13:00")
    delivery_channel: Mapped[str] = mapped_column(String(32), nullable=False, default="LOCAL_OUTBOX")
    box_folder_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class DeliveryRecipient(Base):
    """One of the ten pilot recipient slots; no credentials are stored here."""

    __tablename__ = "delivery_recipients"
    __table_args__ = (UniqueConstraint("slot", name="uq_delivery_recipients_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class DeliverySubscription(Base):
    """Per-recipient delivery toggle and optional cadence override."""

    __tablename__ = "delivery_subscriptions"
    __table_args__ = (
        UniqueConstraint("automation_id", "recipient_id", name="uq_delivery_subscription"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    automation_id: Mapped[int] = mapped_column(ForeignKey("automations.id"), nullable=False, index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("delivery_recipients.id"), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # INHERIT uses the automation cadence; DAILY/WEEKLY can be per person.
    schedule_type: Mapped[str] = mapped_column(String(16), nullable=False, default="INHERIT")
    weekday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_time_utc: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)


class AutomationRun(Base):
    """Append-only execution and delivery evidence for a scheduled task."""

    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    automation_id: Mapped[int] = mapped_column(ForeignKey("automations.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    artifact_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
