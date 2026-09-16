from sqlalchemy import Integer, JSON
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.models.base import Base


class IllumioLabel(Base):

    __tablename__ = "illumio_labels"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    illumio_href: Mapped[str] = mapped_column(
        String(512),
        nullable=True,
        unique=True
    )

    label_type: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    value: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    raw_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True
    )
