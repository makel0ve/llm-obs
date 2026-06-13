import json

from pydantic import SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    environment: str = "development"

    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://llmobs:llmobs@localhost/llmobs"
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10

    redis_url: str = "redis://localhost:6379/0"

    secret_key: SecretStr = SecretStr(
        "dev-secret-key-change-in-production-min-32-chars"
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440

    api_rate_limit_per_minute: int = 1000
    cors_allowed_origins: str | list[str] = "http://localhost:3000"

    s3_bucket: str = "llm-obs-payloads"
    s3_endpoint_url: str | None = None
    aws_access_key_id: SecretStr = SecretStr("")
    aws_secret_access_key: SecretStr = SecretStr("")

    default_retention_days: int = 90

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


settings = Settings()
