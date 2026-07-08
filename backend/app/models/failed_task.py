import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, UUID, BigInteger, Boolean, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FailedTask(Base):
    __tablename__ = "failed_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_args: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int | None] = mapped_column(Integer)
    failed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("TIMEZONE('utc', now())")
    )
    resolved: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
