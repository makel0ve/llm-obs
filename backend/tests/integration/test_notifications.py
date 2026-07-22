import pytest

from app.services.notifications import (
    NotificationService,
    validate_webhook_delivery_url,
)


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
        "notify_slack_webhook": "https://hooks.slack.com/services/demo",
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

    async def fake_slack(rule: dict[str, object], message: str) -> bool:
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

    async def fake_slack(rule: dict[str, object], message: str) -> bool:
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

    async def fake_slack(rule: dict[str, object], message: str) -> bool:
        nonlocal slack_calls
        slack_calls += 1
        return True

    monkeypatch.setattr("app.services.notifications.get_redis", fake_get_redis)
    monkeypatch.setattr(service, "_slack", fake_slack)

    sent = await service.send_alert(_rule(), value=123.0, message="demo")

    assert sent is False
    assert slack_calls == 0
    assert redis.set_calls == []


@pytest.mark.asyncio
async def test_slack_rejects_unsafe_webhook_before_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = NotificationService()
    rule = _rule()
    rule["notify_slack_webhook"] = "https://127.0.0.1/hook"

    def fail_client(*args: object, **kwargs: object) -> None:
        raise AssertionError("unsafe webhook should not reach HTTP client")

    monkeypatch.setattr("app.services.notifications.httpx.AsyncClient", fail_client)

    sent = await service._slack(rule, message="demo")

    assert sent is False


@pytest.mark.asyncio
async def test_webhook_dns_resolution_rejects_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve_webhook_host(hostname: str, port: int) -> set[str]:
        assert hostname == "hooks.slack.com"
        assert port == 443
        return {"10.0.0.5"}

    monkeypatch.setattr(
        "app.services.notifications._resolve_webhook_host",
        fake_resolve_webhook_host,
    )

    with pytest.raises(ValueError, match="DNS resolves"):
        await validate_webhook_delivery_url("https://hooks.slack.com/services/demo")


@pytest.mark.asyncio
async def test_webhook_dns_resolution_rejects_mixed_public_private_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve_webhook_host(hostname: str, port: int) -> set[str]:
        assert hostname == "hooks.slack.com"
        assert port == 443
        return {"93.184.216.34", "10.0.0.5"}

    monkeypatch.setattr(
        "app.services.notifications._resolve_webhook_host",
        fake_resolve_webhook_host,
    )

    with pytest.raises(ValueError, match="DNS resolves"):
        await validate_webhook_delivery_url("https://hooks.slack.com/services/demo")


@pytest.mark.asyncio
async def test_slack_rejects_non_slack_domain_before_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_resolve_webhook_host(hostname: str, port: int) -> set[str]:
        raise AssertionError("non-Slack domains should not reach DNS resolution")

    monkeypatch.setattr(
        "app.services.notifications._resolve_webhook_host",
        fail_resolve_webhook_host,
    )

    with pytest.raises(ValueError, match="official Slack"):
        await validate_webhook_delivery_url("https://example.com/services/demo")


@pytest.mark.asyncio
async def test_slack_rejects_redirect_to_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = NotificationService()
    validated_urls: list[str] = []

    async def fake_validate_webhook_delivery_url(url: str) -> str:
        validated_urls.append(url)
        if url == "https://private.example/hook":
            raise ValueError("Webhook DNS resolves to private or internal addresses")
        return url

    class FakeResponse:
        def __init__(self, *, location: str | None = None) -> None:
            self.headers = {"location": location} if location else {}
            self.is_redirect = location is not None

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.urls: list[str] = []

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(
            self,
            exc_type: object,
            exc: object,
            tb: object,
        ) -> None:
            return None

        async def post(self, url: str, json: object) -> FakeResponse:
            self.urls.append(url)
            if len(self.urls) > 1:
                raise AssertionError("unsafe redirect should not be requested")
            return FakeResponse(location="https://private.example/hook")

    monkeypatch.setattr(
        "app.services.notifications.validate_webhook_delivery_url",
        fake_validate_webhook_delivery_url,
    )
    monkeypatch.setattr("app.services.notifications.httpx.AsyncClient", FakeClient)

    sent = await service._slack(_rule(), message="demo")

    assert sent is False
    assert validated_urls == [
        "https://hooks.slack.com/services/demo",
        "https://hooks.slack.com/services/demo",
        "https://private.example/hook",
    ]
