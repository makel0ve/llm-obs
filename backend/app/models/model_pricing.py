from datetime import datetime
from decimal import Decimal

from sqlalchemy import TIMESTAMP, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ModelPrice(Base):
    __tablename__ = "model_pricing"
    __table_args__ = (UniqueConstraint("provider", "model", "valid_from"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_cost_per_1k_tokens: Mapped[Decimal] = mapped_column(
        Numeric(12, 10), nullable=False
    )
    output_cost_per_1k_tokens: Mapped[Decimal] = mapped_column(
        Numeric(12, 10), nullable=False
    )
    valid_from: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("TIMEZONE('utc', now())"),
        nullable=False,
    )
    valid_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
