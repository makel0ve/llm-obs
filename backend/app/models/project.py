import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    UUID,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("org_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    payload_storage_mode: Mapped[str] = mapped_column(
        String(20), default="all", server_default=text("'all'"), nullable=False
    )
    payload_max_bytes: Mapped[int] = mapped_column(
        Integer, default=262144, server_default=text("262144"), nullable=False
    )
    payload_redact_keys: Mapped[str] = mapped_column(
        Text,
        default="api_key,password,secret,token,authorization",
        server_default=text("'api_key,password,secret,token,authorization'"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("TIMEZONE('utc', now())")
    )
