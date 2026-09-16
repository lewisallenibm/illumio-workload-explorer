from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.models.base import Base


class SyncRun(Base):

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime
    )

    completed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(100)
    )

    records_received: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    records_inserted: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    records_updated: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    records_failed: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=True
    )