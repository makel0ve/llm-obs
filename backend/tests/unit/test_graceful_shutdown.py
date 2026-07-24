from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from fastapi import FastAPI

from app import main as main_module


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> Iterator[None]:
    yield


@pytest.mark.asyncio
async def test_lifespan_closes_runtime_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_ensure_payload_bucket() -> str:
        calls.append("ensure_payload_bucket")
        return "ok"

    async def fake_get_redis() -> object:
        calls.append("get_redis")
        return object()

    class FakePubSubManager:
        async def start(self, redis: object) -> None:
            calls.append("pubsub_start")

        async def stop(self) -> None:
            calls.append("pubsub_stop")

    async def fake_close_redis() -> None:
        calls.append("close_redis")

    async def fake_close_db_engines() -> None:
        calls.append("close_db_engines")

    monkeypatch.setattr(
        main_module,
        "ensure_payload_bucket",
        fake_ensure_payload_bucket,
    )
    monkeypatch.setattr(main_module, "get_redis", fake_get_redis)
    monkeypatch.setattr(main_module, "pubsub_manager", FakePubSubManager())
    monkeypatch.setattr(main_module, "close_redis", fake_close_redis)
    monkeypatch.setattr(main_module, "close_db_engines", fake_close_db_engines)

    async with main_module.lifespan(FastAPI()):
        calls.append("served")

    assert calls == [
        "ensure_payload_bucket",
        "get_redis",
        "pubsub_start",
        "served",
        "pubsub_stop",
        "close_redis",
        "close_db_engines",
    ]


def test_compose_worker_and_api_shutdown_settings() -> None:
    project_root = Path(__file__).resolve().parents[3]

    for compose_file in [
        project_root / "infra/docker-compose.yml",
        project_root / "infra/docker-compose.prod.yml",
    ]:
        compose = yaml.safe_load(compose_file.read_text())
        services: dict[str, dict[str, Any]] = compose["services"]

        assert services["backend"]["stop_grace_period"] == "45s"
        assert services["worker"]["stop_grace_period"] == "45s"
        assert services["scheduler"]["stop_grace_period"] == "20s"

        worker_command = services["worker"]["command"]
        assert "--shutdown-timeout 35" in worker_command
        assert "--wait-tasks-timeout 30" in worker_command

    prod_backend_command = yaml.safe_load(
        (project_root / "infra/docker-compose.prod.yml").read_text()
    )["services"]["backend"]["command"]
    assert "--graceful-timeout 30" in prod_backend_command
    assert "--timeout 60" in prod_backend_command
