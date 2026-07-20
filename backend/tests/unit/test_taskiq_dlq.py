from typing import Any, cast
from urllib.parse import urlparse

import pytest
from taskiq.message import TaskiqMessage
from taskiq.result import TaskiqResult

from app.core import taskiq as taskiq_module
from app.core.config import settings
from app.core.taskiq import DLQRetryMiddleware
from app.workers import dlq as dlq_module


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


def _message(
    *,
    labels: dict[str, Any] | None = None,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> TaskiqMessage:
    return TaskiqMessage(
        task_id="task-1",
        task_name="app.workers.process_span:process_span_batch",
        labels=labels or {"retry_on_error": True, "max_retries": 3},
        args=args or [],
        kwargs=kwargs or {},
    )


def _result() -> TaskiqResult[None]:
    return TaskiqResult(
        is_err=True,
        execution_time=0.1,
        return_value=None,
        error=RuntimeError("boom"),
    )


@pytest.mark.asyncio
async def test_final_retry_failure_is_sent_to_dlq_with_safe_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeHandleFailedTask:
        async def kiq(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(dlq_module, "handle_failed_task", FakeHandleFailedTask())

    middleware = DLQRetryMiddleware(default_retry_count=3)
    await middleware.on_error(
        _message(
            labels={"retry_on_error": True, "max_retries": 3, "_retries": 2},
            kwargs={
                "batch_id": "batch-1",
                "project_id": "project-1",
                "spans": [
                    {
                        "input_messages": [{"content": "secret"}],
                        "output": "private",
                    }
                ],
            },
        ),
        _result(),
        RuntimeError("boom"),
    )

    assert captured == {
        "task_name": "app.workers.process_span:process_span_batch",
        "task_args": {
            "batch_id": "batch-1",
            "project_id": "project-1",
            "span_count": 1,
        },
        "error": "boom",
        "attempts": 3,
    }


@pytest.mark.asyncio
async def test_intermediate_retry_failure_is_not_sent_to_dlq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []
    scheduled: list[float] = []

    class FakeHandleFailedTask:
        async def kiq(self, **kwargs: Any) -> None:
            captured.append(kwargs)

    async def fake_on_send(kicker: Any, message: TaskiqMessage, delay: float) -> None:
        scheduled.append(delay)

    monkeypatch.setattr(dlq_module, "handle_failed_task", FakeHandleFailedTask())

    middleware = DLQRetryMiddleware(default_retry_count=3, default_delay=1)
    monkeypatch.setattr(middleware, "on_send", fake_on_send)

    await middleware.on_error(
        _message(labels={"retry_on_error": True, "max_retries": 3, "_retries": 1}),
        _result(),
        RuntimeError("boom"),
    )

    assert captured == []
    assert scheduled == [1.0]


@pytest.mark.asyncio
async def test_retry_disabled_failure_is_not_sent_to_dlq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []

    class FakeHandleFailedTask:
        async def kiq(self, **kwargs: Any) -> None:
            captured.append(kwargs)

    monkeypatch.setattr(dlq_module, "handle_failed_task", FakeHandleFailedTask())

    middleware = DLQRetryMiddleware(default_retry_count=1)
    await middleware.on_error(
        _message(labels={"retry_on_error": False, "max_retries": 1}),
        _result(),
        RuntimeError("boom"),
    )

    assert captured == []


def test_positional_process_span_args_are_summarized_for_dlq() -> None:
    task_args = taskiq_module._task_args_for_dlq(
        _message(
            args=[
                "batch-1",
                "project-1",
                [{"input_messages": [{"content": "secret"}], "output": "private"}],
            ]
        )
    )

    assert task_args == {
        "batch_id": "batch-1",
        "project_id": "project-1",
        "span_count": 1,
    }


def test_taskiq_uses_durable_queue_redis_for_broker_results_and_dlq() -> None:
    expected_url = urlparse(settings.effective_redis_queue_url)
    expected_connection = {
        "host": expected_url.hostname,
        "port": expected_url.port or 6379,
        "db": int((expected_url.path or "/0").lstrip("/") or "0"),
    }
    broker = cast(Any, taskiq_module.broker)
    result_backend = cast(Any, broker.result_backend)
    dlq_broker = cast(Any, taskiq_module.dlq_broker)

    assert broker.connection_pool.connection_kwargs == expected_connection
    assert result_backend.redis_pool.connection_kwargs == expected_connection
    assert dlq_broker.connection_pool.connection_kwargs == expected_connection
    assert dlq_broker.queue_name == "llm-obs-dlq"
