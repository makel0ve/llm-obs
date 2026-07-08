import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

ALLOWED_PROVIDERS = frozenset(
    {
        "openai",
        "anthropic",
        "gigachat",
        "yandexgpt",
        "ollama",
        "gemini",
        "mistral",
        "cohere",
        "custom",
    }
)


def validate_uuid_string(value: str | None, field_name: str) -> str | None:
    if value is None:
        return value

    try:
        uuid.UUID(value)
    except ValueError:
        raise ValueError(f"{field_name} must be a valid UUID") from None

    return value


class SpanSchema(BaseModel):
    span_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = Field(min_length=1, max_length=64)
    parent_span_id: str | None = Field(default=None, max_length=64)
    name: str = Field(default="llm_call", max_length=255)
    provider: str = Field(max_length=50)
    model: str = Field(max_length=100)
    input_messages: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    output: str | None = Field(default=None, max_length=100_000)
    error: str | None = Field(default=None, max_length=10_000)
    input_tokens: int = Field(ge=0, le=10_000_000, default=0)
    output_tokens: int = Field(ge=0, le=10_000_000, default=0)
    latency_ms: float = Field(ge=0, le=3_600_000)
    started_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("span_id", "trace_id", "parent_span_id")
    @classmethod
    def validate_uuid_fields(cls, v: str | None, info: ValidationInfo) -> str | None:
        return validate_uuid_string(v, info.field_name or "field")

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, v: str) -> str:
        v = v.lower().strip()
        return v if v in ALLOWED_PROVIDERS else "custom"

    @field_validator("started_at")
    @classmethod
    def no_future_timestamps(cls, v: datetime) -> datetime:
        v_utc = v if v.tzinfo else v.replace(tzinfo=UTC)
        now = datetime.now(UTC)

        if v_utc > now + timedelta(minutes=5):
            raise ValueError(
                "started_at cannot be in the future (max 5 min clock skew)"
            )

        return v

    @field_validator("metadata")
    @classmethod
    def limit_metadata_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(str(v)) > 10_000:
            raise ValueError("metadata exceeds 10KB limit")

        return v


class IngestRequest(BaseModel):
    spans: list[SpanSchema] = Field(min_length=1, max_length=100)
    idempotency_key: str | None = Field(default=None, max_length=128)


class IngestResponse(BaseModel):
    batch_id: str
    accepted: int


class BatchStatusResponse(BaseModel):
    batch_id: str
    status: Literal["accepted", "processing", "processed", "partial_failed", "failed"]
    accepted: int
    processed: int
    failed: int
    error: str | None = None
    created_at: datetime
    updated_at: datetime
