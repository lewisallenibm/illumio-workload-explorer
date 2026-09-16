from typing import Optional

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.models.base import Base


class Workload(Base):
    __tablename__ = "workloads"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    import_run_id: Mapped[int] = mapped_column(
        ForeignKey("import_runs.id")
    )

    hostname: Mapped[str] = mapped_column(
        String(255),
        index=True
    )

    app: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    env: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    loc: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    role: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    district: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    region: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    enforcement: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    online: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )

    agent_status: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    agent_health: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    last_heartbeat_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime,
        nullable=True
    )

    raw_interfaces: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    ips = relationship(
        "WorkloadIP",
        back_populates="workload"
    )