import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import failed_tasks as failed_tasks_api
from app.api.v1.failed_tasks import (
    list_failed_tasks,
    resolve_failed_task,
    retry_failed_task,
)
from app.services.failed_tasks import record_failed_task, summarize_task_args


class FakeResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def one_or_none(self):
        return self._one

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeDb:
    def __init__(self, *, org_id=None, rows=None, project_exists=True, retry_row=None):
        self.org_id = org_id
        self.rows = rows or []
        self.project_exists = project_exists
        self.retry_row = retry_row
        self.params = []
        self.committed = False

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.params.append(params or {})

        if "SELECT org_id FROM projects" in sql:
            row = {"org_id": self.org_id} if self.org_id else None
            return FakeResult(one=row)

        if "SELECT id FROM projects" in sql:
            row = {"id": params["pid"]} if self.project_exists else None
            return FakeResult(one=row)

        if "SELECT id, task_name, project_id, task_args, resolved" in sql:
            return FakeResult(one=self.retry_row)

        if "SELECT id, task_name" in sql:
            return FakeResult(rows=self.rows)

        if "UPDATE failed_tasks" in sql:
            return FakeResult(one={"id": params["task_id"]})

        return FakeResult()

    async def commit(self):
        self.committed = True


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


def _user(role="admin", org_id=None):
    return {
        "sub": str(uuid4()),
        "org_id": org_id or str(uuid4()),
        "role": role,
    }


def test_summarize_task_args_redacts_payload_and_secrets():
    summary = summarize_task_args(
        {
            "batch_id": "batch-1",
            "project_id": "project-1",
            "api_key": "secret",
            "spans": [
                {"input_messages": [{"content": "private"}], "output": "private"},
                {"input_messages": [{"content": "private"}]},
            ],
            "metadata": {"nested": True},
        }
    )

    assert summary == {
        "batch_id": "batch-1",
        "project_id": "project-1",
        "api_key": "[redacted]",
        "span_count": 2,
        "metadata": "<dict>",
    }


@pytest.mark.asyncio
async def test_record_failed_task_stores_scope_and_safe_args():
    org_id = str(uuid4())
    project_id = str(uuid4())
    db = FakeDb(org_id=org_id)

    await record_failed_task(
        db,
        task_name="process_span_batch",
        task_args={
            "batch_id": "batch-1",
            "project_id": project_id,
            "spans": [{"input_messages": [{"content": "private"}]}],
        },
        error="boom",
        attempts=3,
        failed_at=datetime.now(UTC),
    )

    insert_params = db.params[-1]
    args_summary = json.loads(insert_params["args"])
    assert insert_params["org_id"] == org_id
    assert insert_params["project_id"] == project_id
    assert args_summary == {
        "batch_id": "batch-1",
        "project_id": project_id,
        "span_count": 1,
    }


@pytest.mark.asyncio
async def test_list_failed_tasks_requires_admin():
    with pytest.raises(HTTPException) as exc_info:
        await list_failed_tasks(user=_user(role="member"))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_failed_tasks_scopes_to_user_org(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    db = FakeDb(
        rows=[
            {
                "id": 1,
                "task_name": "process_span_batch",
                "project_id": project_id,
                "task_args": json.dumps({"batch_id": "batch-1", "span_count": 2}),
                "error": "boom",
                "attempts": 3,
                "failed_at": datetime.now(UTC),
                "resolved": False,
            }
        ]
    )

    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(failed_tasks_api, "get_db", fake_get_db)

    result = await list_failed_tasks(
        project_id=project_id, limit=100, user=_user(org_id=org_id)
    )

    assert result[0]["task_args"] == {"batch_id": "batch-1", "span_count": 2}
    assert db.params[-1] == {
        "org": org_id,
        "project_id": project_id,
        "include_resolved": False,
        "limit": 100,
    }


@pytest.mark.asyncio
async def test_list_failed_tasks_allows_missing_project_filter(monkeypatch):
    org_id = str(uuid4())
    db = FakeDb()

    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(failed_tasks_api, "get_db", fake_get_db)

    result = await list_failed_tasks(limit=100, user=_user(org_id=org_id))

    assert result == []
    assert db.params[-1] == {
        "org": org_id,
        "project_id": None,
        "include_resolved": False,
        "limit": 100,
    }


@pytest.mark.asyncio
async def test_resolve_failed_task_scopes_to_user_org(monkeypatch):
    org_id = str(uuid4())
    db = FakeDb()

    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(failed_tasks_api, "get_db", fake_get_db)

    result = await resolve_failed_task(task_id=42, user=_user(org_id=org_id))

    assert result.resolved is True
    assert db.params[-1] == {"task_id": 42, "org": org_id}
    assert db.committed is True


@pytest.mark.asyncio
async def test_retry_failed_task_requeues_retryable_span_batch(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    spans = [{"span_id": str(uuid4()), "provider": "openai"}]
    db = FakeDb(
        retry_row={
            "id": 42,
            "task_name": "process_span_batch",
            "project_id": project_id,
            "task_args": json.dumps(
                {"batch_id": "batch-1", "project_id": project_id, "spans": spans}
            ),
            "resolved": False,
        }
    )
    enqueued = {}

    class FakeProcessSpanBatch:
        async def kiq(self, **kwargs):
            enqueued.update(kwargs)

    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(failed_tasks_api, "get_db", fake_get_db)
    monkeypatch.setattr(failed_tasks_api, "process_span_batch", FakeProcessSpanBatch())

    result = await retry_failed_task(task_id=42, user=_user(org_id=org_id))

    assert result.retried is True
    assert enqueued == {
        "batch_id": "batch-1",
        "project_id": project_id,
        "spans": spans,
    }
    assert db.params[-1] == {"task_id": 42, "org": org_id}
    assert db.committed is True


@pytest.mark.asyncio
async def test_retry_failed_task_accepts_full_taskiq_task_name(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    spans = [{"span_id": str(uuid4()), "provider": "openai"}]
    db = FakeDb(
        retry_row={
            "id": 42,
            "task_name": "app.workers.process_span:process_span_batch",
            "project_id": project_id,
            "task_args": json.dumps(
                {"batch_id": "batch-1", "project_id": project_id, "spans": spans}
            ),
            "resolved": False,
        }
    )
    enqueued = {}

    class FakeProcessSpanBatch:
        async def kiq(self, **kwargs):
            enqueued.update(kwargs)

    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(failed_tasks_api, "get_db", fake_get_db)
    monkeypatch.setattr(failed_tasks_api, "process_span_batch", FakeProcessSpanBatch())

    result = await retry_failed_task(task_id=42, user=_user(org_id=org_id))

    assert result.retried is True
    assert enqueued == {
        "batch_id": "batch-1",
        "project_id": project_id,
        "spans": spans,
    }


@pytest.mark.asyncio
async def test_retry_failed_task_rejects_summary_only_task_args(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    db = FakeDb(
        retry_row={
            "id": 42,
            "task_name": "process_span_batch",
            "project_id": project_id,
            "task_args": json.dumps(
                {"batch_id": "batch-1", "project_id": project_id, "span_count": 2}
            ),
            "resolved": False,
        }
    )

    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(failed_tasks_api, "get_db", fake_get_db)

    with pytest.raises(HTTPException) as exc_info:
        await retry_failed_task(task_id=42, user=_user(org_id=org_id))

    assert exc_info.value.status_code == 409
    assert "payload is not available" in exc_info.value.detail


@pytest.mark.asyncio
async def test_dlq_recovery_runbook_smoke_lists_rejects_retry_and_resolves(
    monkeypatch,
):
    org_id = str(uuid4())
    project_id = str(uuid4())
    failed_at = datetime.now(UTC)
    db = FakeDb(
        rows=[
            {
                "id": 42,
                "task_name": "app.workers.process_span:process_span_batch",
                "project_id": project_id,
                "task_args": json.dumps(
                    {
                        "batch_id": "batch-1",
                        "project_id": project_id,
                        "span_count": 2,
                    }
                ),
                "error": "permanent failure",
                "attempts": 3,
                "failed_at": failed_at,
                "resolved": False,
            }
        ],
        retry_row={
            "id": 42,
            "task_name": "app.workers.process_span:process_span_batch",
            "project_id": project_id,
            "task_args": json.dumps(
                {
                    "batch_id": "batch-1",
                    "project_id": project_id,
                    "span_count": 2,
                }
            ),
            "resolved": False,
        },
    )

    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(failed_tasks_api, "get_db", fake_get_db)

    tasks = await list_failed_tasks(
        project_id=project_id,
        limit=100,
        user=_user(org_id=org_id),
    )
    assert tasks == [
        {
            "id": 42,
            "task_name": "app.workers.process_span:process_span_batch",
            "project_id": project_id,
            "task_args": {
                "batch_id": "batch-1",
                "project_id": project_id,
                "span_count": 2,
            },
            "error": "permanent failure",
            "attempts": 3,
            "failed_at": failed_at,
            "resolved": False,
        }
    ]

    with pytest.raises(HTTPException) as exc_info:
        await retry_failed_task(task_id=42, user=_user(org_id=org_id))
    assert exc_info.value.status_code == 409
    assert "payload is not available" in exc_info.value.detail

    result = await resolve_failed_task(task_id=42, user=_user(org_id=org_id))
    assert result.resolved is True
    assert db.committed is True
