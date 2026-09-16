from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.models.base import Base


class WorkloadIP(Base):
    __tablename__ = "workload_ips"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    workload_id: Mapped[int] = mapped_column(
        ForeignKey("workloads.id")
    )

    interface_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    ip_address: Mapped[str] = mapped_column(
        String(64),
        index=True
    )

    workload = relationship(
        "Workload",
        back_populates="ips"
    )