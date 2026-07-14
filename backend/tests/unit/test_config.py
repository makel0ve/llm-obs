import pytest
from pydantic import ValidationError

from app.core.config import Settings


def production_settings(**overrides: str) -> Settings:
    values: dict[str, str] = {
        "environment": "production",
        "secret_key": "f" * 64,
        "database_url": "postgresql+asyncpg://app:strong-pass@pgbouncer:6432/llmobs",
        "redis_url": "redis://redis:6379/0",
        "cors_allowed_origins": "https://dashboard.example.com",
        "s3_endpoint_url": "http://minio:9000",
        "aws_access_key_id": "prod-minio-access",
        "aws_secret_access_key": "prod-minio-secret",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_development_defaults_remain_valid() -> None:
    settings = Settings()

    assert settings.environment == "development"


def test_production_settings_accept_safe_values() -> None:
    settings = production_settings()

    assert settings.environment == "production"
    assert settings.cors_allowed_origins == ["https://dashboard.example.com"]


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        (
            "secret_key",
            "dev-secret-key-change-in-production-min-32-chars",
            "secret_key",
        ),
        ("secret_key", "replace-with-random-64-hex-character-secret", "secret_key"),
        ("aws_access_key_id", "minioadmin", "aws_access_key_id"),
        ("aws_access_key_id", "replace-with-s3-access-key", "aws_access_key_id"),
        ("aws_secret_access_key", "minioadmin123", "aws_secret_access_key"),
        (
            "aws_secret_access_key",
            "replace-with-s3-secret-key",
            "aws_secret_access_key",
        ),
    ],
)
def test_production_rejects_placeholder_secrets(
    field: str,
    value: str,
    match: str,
) -> None:
    with pytest.raises(ValidationError, match=match):
        production_settings(**{field: value})


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        (
            "database_url",
            "postgresql+asyncpg://app:pass@localhost:5432/llmobs",
            "database_url",
        ),
        ("redis_url", "redis://127.0.0.1:6379/0", "redis_url"),
        ("s3_endpoint_url", "http://localhost:9000", "s3_endpoint_url"),
    ],
)
def test_production_rejects_local_service_urls(
    field: str,
    value: str,
    match: str,
) -> None:
    with pytest.raises(ValidationError, match=match):
        production_settings(**{field: value})


@pytest.mark.parametrize("origins", ["*", "http://localhost:3000"])
def test_production_rejects_unsafe_cors_origins(origins: str) -> None:
    with pytest.raises(ValidationError, match="cors_allowed_origins"):
        production_settings(cors_allowed_origins=origins)
