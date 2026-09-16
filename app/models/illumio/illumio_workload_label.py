from sqlalchemy import ForeignKey

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.models.base import Base


class IllumioWorkloadLabel(Base):

    __tablename__ = "illumio_workload_labels"

    workload_id: Mapped[int] = mapped_column(
        ForeignKey("illumio_workloads.id"),
        primary_key=True,
    )

    label_id: Mapped[int] = mapped_column(
        ForeignKey("illumio_labels.id"),
        primary_key=True,
    )

    workload = relationship(
        "IllumioWorkload",
        back_populates="labels",
    )

    label = relationship(
        "IllumioLabel",
    )