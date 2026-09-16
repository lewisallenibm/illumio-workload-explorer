from sqlalchemy import ForeignKey, JSON
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.models.base import Base


class IllumioInterface(Base):

    __tablename__ = "illumio_interfaces"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    workload_id: Mapped[int] = mapped_column(
        ForeignKey(
            "illumio_workloads.id"
        ),
        index=True
    )

    interface_name: Mapped[str] = mapped_column(
        String(255)
    )

    ip_address: Mapped[str] = mapped_column(
        String(255),
        index=True
    )

    network_name_or_type: Mapped[str] = mapped_column(
        String(255),
        nullable=True
    )

    raw_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True
    )

    workload = relationship(
        "IllumioWorkload",
        back_populates="interfaces"
    )
