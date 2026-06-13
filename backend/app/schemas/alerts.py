from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class AlertRuleCreate(BaseModel):
    project_id: str
    name: str
    metric: Literal["latency_p95", "error_rate", "cost_hourly", "anomaly"]
    condition: Literal["gt", "lt", "anomaly"]
    threshold: Decimal | None = None
    window_minutes: int = 5
    cooldown_minutes: int = 15
    notify_slack_webhook: str | None = None
    notify_email: str | None = None


class AlertRuleUpdate(BaseModel):
    is_active: bool | None = None
    threshold: Decimal | None = None
    notify_slack_webhook: str | None = None
    notify_email: str | None = None
