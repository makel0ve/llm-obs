import ipaddress
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

AlertMetric = Literal["latency_p95", "error_rate", "cost_hourly", "anomaly"]
AlertCondition = Literal["gt", "lt", "anomaly"]


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()
    return value or None


def _validate_https_webhook(value: str | None) -> str | None:
    value = _normalize_optional_string(value)
    if value is None:
        return None

    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Slack webhook must be an HTTPS URL")

    hostname = parsed.hostname.lower().strip("[]")
    if hostname == "localhost" or hostname.endswith(".local"):
        raise ValueError("Slack webhook cannot target localhost or local hosts")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return value

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise ValueError("Slack webhook cannot target private or internal addresses")

    return value


def _validate_threshold_for_metric(
    metric: AlertMetric, condition: AlertCondition, threshold: Decimal | None
) -> None:
    if metric == "anomaly" or condition == "anomaly":
        return

    if threshold is None:
        raise ValueError("threshold is required for non-anomaly alert rules")

    if threshold <= 0:
        raise ValueError("threshold must be greater than 0")


class AlertRuleCreate(BaseModel):
    project_id: str
    name: str
    metric: AlertMetric
    condition: AlertCondition
    threshold: Decimal | None = None
    window_minutes: int = Field(default=5, ge=1)
    cooldown_minutes: int = Field(default=15, ge=1)
    notify_slack_webhook: str | None = None
    notify_email: EmailStr | None = None

    @field_validator("notify_slack_webhook")
    @classmethod
    def validate_slack_webhook(cls, v: str | None) -> str | None:
        return _validate_https_webhook(v)

    @field_validator("notify_email", mode="before")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        return _normalize_optional_string(v)

    @model_validator(mode="after")
    def validate_rule(self) -> "AlertRuleCreate":
        _validate_threshold_for_metric(self.metric, self.condition, self.threshold)
        if not self.notify_slack_webhook and not self.notify_email:
            raise ValueError("at least one notification target is required")

        return self


class AlertRuleUpdate(BaseModel):
    is_active: bool | None = None
    threshold: Decimal | None = None
    notify_slack_webhook: str | None = None
    notify_email: EmailStr | None = None

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("threshold must be greater than 0")

        return v

    @field_validator("notify_slack_webhook")
    @classmethod
    def validate_slack_webhook(cls, v: str | None) -> str | None:
        return _validate_https_webhook(v)

    @field_validator("notify_email", mode="before")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        return _normalize_optional_string(v)
