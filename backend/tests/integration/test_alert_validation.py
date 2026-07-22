from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.alerts import AlertRuleCreate, AlertRuleUpdate


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


def _valid_rule(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_id": "project-1",
        "name": "High latency",
        "metric": "latency_p95",
        "condition": "gt",
        "threshold": Decimal("500"),
        "window_minutes": 5,
        "cooldown_minutes": 15,
        "notify_email": "alerts@example.com",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "webhook",
    [
        "http://hooks.slack.com/services/demo",
        "https://localhost/services/demo",
        "https://127.0.0.1/services/demo",
        "https://10.0.0.5/services/demo",
        "https://172.16.0.1/services/demo",
        "https://192.168.1.1/services/demo",
        "https://[::1]/services/demo",
        "https://alerts.local/services/demo",
        "https://hooks.slack.com:8443/services/demo",
        "https://example.com/services/demo",
        "https://hooks.evil-slack.com/services/demo",
    ],
)
def test_alert_rule_rejects_unsafe_slack_webhook_targets(webhook: str) -> None:
    with pytest.raises(ValidationError):
        AlertRuleCreate.model_validate(
            _valid_rule(notify_email=None, notify_slack_webhook=webhook)
        )


def test_alert_rule_accepts_https_public_slack_webhook() -> None:
    rule = AlertRuleCreate.model_validate(
        _valid_rule(
            notify_email=None,
            notify_slack_webhook="https://hooks.slack.com/services/demo",
        )
    )

    assert rule.notify_slack_webhook == "https://hooks.slack.com/services/demo"


def test_alert_rule_accepts_govslack_webhook_domain() -> None:
    rule = AlertRuleCreate.model_validate(
        _valid_rule(
            notify_email=None,
            notify_slack_webhook="https://hooks.slack-gov.com/services/demo",
        )
    )

    assert rule.notify_slack_webhook == "https://hooks.slack-gov.com/services/demo"


@pytest.mark.parametrize(
    "field,value",
    [
        ("window_minutes", 0),
        ("cooldown_minutes", 0),
        ("threshold", Decimal("0")),
    ],
)
def test_alert_rule_rejects_non_positive_constraints(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        AlertRuleCreate.model_validate(_valid_rule(**{field: value}))


def test_alert_rule_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        AlertRuleCreate.model_validate(_valid_rule(notify_email="not-an-email"))


def test_alert_rule_requires_target() -> None:
    with pytest.raises(ValidationError, match="notification target"):
        AlertRuleCreate.model_validate(
            _valid_rule(notify_email=None, notify_slack_webhook=None)
        )


def test_anomaly_rule_allows_missing_threshold() -> None:
    rule = AlertRuleCreate.model_validate(
        _valid_rule(metric="anomaly", condition="anomaly", threshold=None)
    )

    assert rule.threshold is None


def test_alert_rule_update_normalizes_empty_targets() -> None:
    update = AlertRuleUpdate(notify_email="", notify_slack_webhook="")

    assert update.notify_email is None
    assert update.notify_slack_webhook is None


def test_alert_rule_update_rejects_unsafe_webhook() -> None:
    with pytest.raises(ValidationError):
        AlertRuleUpdate(notify_slack_webhook="https://169.254.169.254/hook")


def test_alert_rule_update_rejects_non_slack_webhook_domain() -> None:
    with pytest.raises(ValidationError):
        AlertRuleUpdate(notify_slack_webhook="https://example.com/hook")
