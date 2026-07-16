import pytest

from app.services.notifications import NotificationService


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


class FakeRedis:
    def __init__(self, existing: str | None = None) -> None:
        self.value = existing
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str) -> str | None:
        assert key == "alert_cooldown:rule-1"
        return self.value

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.set_calls.append((key, value, ex))
        self.value = value
        return True


def _rule() -> dict[str, object]:
    return {
        "id": "rule-1",
        "name": "High latency",
        "cooldown_minutes": 15,
        "notify_slack_webhook": "https://hooks.slack.test/demo",
        "notify_email": None,
    }


@pytest.mark.asyncio
async def test_failed_alert_delivery_does_not_record_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    service = NotificationService()
    slack_calls = 0

    async def fake_get_redis() -> FakeRedis:
        return redis

    async def fake_slack(rule: dict, message: str) -> bool:
        nonlocal slack_calls
        slack_calls += 1
        return False

    monkeypatch.setattr("app.services.notifications.get_redis", fake_get_redis)
    monkeypatch.setattr(service, "_slack", fake_slack)

    sent = await service.send_alert(_rule(), value=123.0, message="demo")

    assert sent is False
    assert slack_calls == 1
    assert redis.set_calls == []


@pytest.mark.asyncio
async def test_successful_alert_delivery_records_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    service = NotificationService()

    async def fake_get_redis() -> FakeRedis:
        return redis

    async def fake_slack(rule: dict, message: str) -> bool:
        return True

    monkeypatch.setattr("app.services.notifications.get_redis", fake_get_redis)
    monkeypatch.setattr(service, "_slack", fake_slack)

    sent = await service.send_alert(_rule(), value=123.0, message="demo")

    assert sent is True
    assert redis.set_calls == [("alert_cooldown:rule-1", "1", 900)]


@pytest.mark.asyncio
async def test_existing_alert_cooldown_suppresses_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis(existing="1")
    service = NotificationService()
    slack_calls = 0

    async def fake_get_redis() -> FakeRedis:
        return redis

    async def fake_slack(rule: dict, message: str) -> bool:
        nonlocal slack_calls
        slack_calls += 1
        return True

    monkeypatch.setattr("app.services.notifications.get_redis", fake_get_redis)
    monkeypatch.setattr(service, "_slack", fake_slack)

    sent = await service.send_alert(_rule(), value=123.0, message="demo")

    assert sent is False
    assert slack_calls == 0
    assert redis.set_calls == []
