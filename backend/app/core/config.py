import json
from typing import Self
from urllib.parse import urlparse

from pydantic import SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PRODUCTION_PLACEHOLDER_SECRETS = {
    "",
    "change-me",
    "changeme",
    "minioadmin",
    "minioadmin123",
    "password",
    "your-minio-password",
    "your-postgres-password",
    "your-random-32-char-secret-key-here",
    "dev-secret-key-change-in-production-min-32-chars",
}


def _secret_value(value: SecretStr) -> str:
    return value.get_secret_value()


def _contains_localhost(value: str) -> bool:
    parsed = urlparse(value)
    host = parsed.hostname or value
    return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    environment: str = "development"

    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://llmobs:llmobs@localhost/llmobs"
    )
    migration_database_url: SecretStr | None = None
    database_pool_size: int = 20
    database_max_overflow: int = 10
    postgres_user: str = "llmobs"
    postgres_app_user: str = "llmobs_app"
    postgres_app_password: SecretStr = SecretStr("")

    redis_url: str = "redis://localhost:6379/0"
    redis_queue_url: str | None = None

    secret_key: SecretStr = SecretStr(
        "dev-secret-key-change-in-production-min-32-chars"
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440
    public_registration_enabled: bool = True
    bootstrap_admin_token: SecretStr | None = None

    api_rate_limit_per_minute: int = 1000
    auth_rate_limit_per_minute: int = 20
    auth_rate_limit_window_seconds: int = 60
    max_request_body_bytes: int = 10 * 1024 * 1024
    cors_allowed_origins: str | list[str] = "http://localhost:3000"

    s3_bucket: str = "llm-obs-payloads"
    s3_endpoint_url: str | None = None
    aws_access_key_id: SecretStr = SecretStr("")
    aws_secret_access_key: SecretStr = SecretStr("")

    default_retention_days: int = 90
    worker_heartbeat_max_age_seconds: int = 180
    worker_heartbeat_ttl_seconds: int = 300

    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = "alerts@llm-obs.io"

    @field_validator("database_url")
    @classmethod
    def no_localhost_in_prod(cls, v: SecretStr, info: ValidationInfo) -> SecretStr:
        if (
            info.data.get("environment") == "production"
            and "localhost" in v.get_secret_value()
        ):
            raise ValueError("Production DB URL cannot point to localhost")

        return v

    @field_validator("secret_key")
    @classmethod
    def secret_key_not_empty(cls, v: SecretStr, info: ValidationInfo) -> SecretStr:
        val = v.get_secret_value()
        if not val:
            raise ValueError("secret_key cannot be empty")

        if info.data.get("environment") == "production" and len(val) < 32:
            raise ValueError("secret_key must be at least 32 characters in production")

        return v

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed

            except (json.JSONDecodeError, ValueError):
                pass

            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def validate_production_environment(self) -> Self:
        if self.environment != "production":
            return self

        self._validate_production_secret("secret_key", self.secret_key, min_length=32)
        if self.bootstrap_admin_token:
            self._validate_production_secret(
                "bootstrap_admin_token",
                self.bootstrap_admin_token,
                min_length=32,
            )
        self._validate_production_secret("aws_access_key_id", self.aws_access_key_id)
        self._validate_production_secret(
            "aws_secret_access_key",
            self.aws_secret_access_key,
        )
        database_url = _secret_value(self.database_url)
        self._validate_production_url("database_url", database_url)
        self._validate_database_url_secret("database_url", database_url)
        self._validate_runtime_database_role(database_url)
        if self.migration_database_url:
            migration_database_url = _secret_value(self.migration_database_url)
            self._validate_production_url(
                "migration_database_url",
                migration_database_url,
            )
            self._validate_database_url_secret(
                "migration_database_url",
                migration_database_url,
            )
        self._validate_production_url("redis_url", self.redis_url)
        self._validate_production_url("redis_queue_url", self.effective_redis_queue_url)
        if self.s3_endpoint_url:
            self._validate_production_url("s3_endpoint_url", self.s3_endpoint_url)

        if not self.cors_allowed_origins:
            raise ValueError("cors_allowed_origins must be set in production")

        for origin in self.cors_allowed_origins:
            if origin == "*":
                raise ValueError(
                    "cors_allowed_origins cannot include '*' in production"
                )
            if _contains_localhost(origin):
                raise ValueError(
                    "cors_allowed_origins cannot include localhost in production"
                )

        return self

    @staticmethod
    def _validate_production_secret(
        name: str,
        value: SecretStr,
        *,
        min_length: int = 1,
    ) -> None:
        secret = _secret_value(value)
        if len(secret) < min_length:
            raise ValueError(
                f"{name} must be at least {min_length} characters in production"
            )
        lowered = secret.lower()
        if lowered in PRODUCTION_PLACEHOLDER_SECRETS or lowered.startswith(
            "replace-with"
        ):
            raise ValueError(f"{name} must not use a placeholder value in production")

    @staticmethod
    def _validate_production_url(name: str, value: str) -> None:
        if not value:
            raise ValueError(f"{name} must be set in production")
        if _contains_localhost(value):
            raise ValueError(f"{name} cannot point to localhost in production")

    def _validate_runtime_database_role(self, database_url: str) -> None:
        runtime_user = urlparse(database_url).username
        if not runtime_user:
            raise ValueError("database_url must include a runtime database user")
        if runtime_user in {self.postgres_user, "postgres"}:
            raise ValueError(
                "database_url must use a dedicated non-owner runtime database role"
            )

    @staticmethod
    def _validate_database_url_secret(name: str, value: str) -> None:
        parsed = urlparse(value)
        password = parsed.password or ""
        lowered = password.lower()
        if lowered in PRODUCTION_PLACEHOLDER_SECRETS or lowered.startswith(
            "replace-with"
        ):
            raise ValueError(f"{name} must not use a placeholder password")

    @property
    def effective_redis_queue_url(self) -> str:
        return self.redis_queue_url or self.redis_url

    @property
    def effective_migration_database_url(self) -> SecretStr:
        return self.migration_database_url or self.database_url


settings = Settings()
