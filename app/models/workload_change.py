from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.models.base import Base


class WorkloadChange(Base):

    __tablename__ = "workload_changes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    workload_id: Mapped[int] = mapped_column(
        ForeignKey("workloads.id")
    )

    field_name: Mapped[str] = mapped_column(
        String(100)
    )

    old_value: Mapped[str] = mapped_column(
        String(255)
    )

    new_value: Mapped[str] = mapped_column(
        String(255)
    )

    # Actor identity (L-2) — Cloudflare Access email or local username.
    actor: Mapped[str] = mapped_column(
        String(320),
        nullable=True,
        default="unknown"
    )

    changed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )