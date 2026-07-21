import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TypedDict
from uuid import uuid4

import pytest

from app.workers import maintenance


class RetentionSpan(TypedDict):
    id: str
    trace_id: str
    started_at: datetime
    payload_s3_key: str | None


class RetentionTrace(TypedDict):
    id: str
    started_at: datetime


class FakeResult:
    def __init__(
        self, rows: list[dict[str, object]] | None = None, rowcount: int = 0
    ) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows


class FakeDb:
    def __init__(self, state: "RetentionState", project_context: str | None) -> None:
        self._state = state
        self._project_context = project_context

    async def execute(
        self, statement: object, params: dict | None = None
    ) -> FakeResult:
        sql = str(statement)
        params = params or {}

        if "SELECT id, retention_days FROM projects" in sql:
            return FakeResult(
                [
                    {
                        "id": self._state.project_id,
                        "retention_days": self._state.retention_days,
                    }
                ]
            )

        if "SELECT id, started_at, payload_s3_key" in sql:
            assert self._project_context == self._state.project_id
            batch = [
                span
                for span in self._state.spans
                if self._state.span_key(span) not in self._state.deleted_span_keys
                and span["started_at"] < params["cutoff"]
            ][: int(params["limit"])]
            return FakeResult([dict(span) for span in batch])

        if "DELETE FROM spans" in sql:
            assert self._project_context == self._state.project_id
            span_keys = {
                (str(row["id"]), datetime.fromisoformat(str(row["started_at"])))
                for row in json.loads(str(params["span_keys"]))
            }
            deleted = [
                span
                for span in self._state.spans
                if self._state.span_key(span) in span_keys
                and self._state.span_key(span) not in self._state.deleted_span_keys
            ]
            self._state.deleted_span_keys.update(
                self._state.span_key(span) for span in deleted
            )
            self._state.deleted_span_ids.update(span["id"] for span in deleted)
            return FakeResult(rowcount=len(deleted))

        if "DELETE FROM traces" in sql:
            assert self._project_context == self._state.project_id
            stale_traces = [
                trace
                for trace in self._state.traces
                if trace["started_at"] < params["cutoff"]
                and trace["id"] not in self._state.deleted_trace_ids
                and not any(
                    span["trace_id"] == trace["id"]
                    and self._state.span_key(span) not in self._state.deleted_span_keys
                    for span in self._state.spans
                )
            ]
            self._state.deleted_trace_ids.update(trace["id"] for trace in stale_traces)
            self._state.deleted_traces += len(stale_traces)
            return FakeResult(rowcount=len(stale_traces))

        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self) -> None:
        return None


class RetentionState:
    def __init__(self) -> None:
        self.project_id = str(uuid4())
        self.retention_days = 7
        self.expired_started_at = datetime.now(UTC) - timedelta(days=8)
        self.fresh_started_at = datetime.now(UTC) - timedelta(days=1)
        expired_trace_id = str(uuid4())
        self.spans: list[RetentionSpan] = [
            {
                "id": str(uuid4()),
                "trace_id": expired_trace_id,
                "started_at": self.expired_started_at,
                "payload_s3_key": f"payloads/{self.project_id}/aa/1.json.gz",
            },
            {
                "id": str(uuid4()),
                "trace_id": expired_trace_id,
                "started_at": self.expired_started_at,
                "payload_s3_key": None,
            },
        ]
        self.traces: list[RetentionTrace] = [
            {"id": expired_trace_id, "started_at": self.expired_started_at},
        ]
        self.deleted_span_ids: set[str] = set()
        self.deleted_span_keys: set[tuple[str, datetime]] = set()
        self.deleted_trace_ids: set[str] = set()
        self.deleted_traces = 0
        self.db_contexts: list[str | None] = []
        self.deleted_payload_keys: list[str] = []

    @staticmethod
    def span_key(span: RetentionSpan) -> tuple[str, datetime]:
        return (span["id"], span["started_at"])

    def get_db(self, project_id: str | None = None) -> FakeDb:
        self.db_contexts.append(project_id)
        return FakeDb(self, project_id)


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


def test_project_payload_key_guard() -> None:
    project_id = str(uuid4())

    assert maintenance._is_project_payload_key(
        project_id, f"payloads/{project_id}/ab/span.json.gz"
    )
    assert not maintenance._is_project_payload_key(
        project_id, "payloads/other/span.json.gz"
    )
    assert not maintenance._is_project_payload_key(
        project_id, "../payloads/span.json.gz"
    )


@pytest.mark.asyncio
async def test_retention_deletes_payload_objects_spans_and_stale_traces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = RetentionState()

    @asynccontextmanager
    async def fake_get_db(project_id: str | None = None):
        yield state.get_db(project_id)

    async def fake_delete_s3_objects(project_id: str, keys: list[str]) -> set[str]:
        assert project_id == state.project_id
        state.deleted_payload_keys.extend(keys)
        return set(keys)

    monkeypatch.setattr(maintenance, "get_db", fake_get_db)
    monkeypatch.setattr(maintenance, "_delete_s3_objects", fake_delete_s3_objects)

    await maintenance.run_data_retention.original_func()

    assert state.deleted_payload_keys == [str(state.spans[0]["payload_s3_key"])]
    assert state.deleted_span_ids == {span["id"] for span in state.spans}
    assert state.deleted_traces == 1
    assert None in state.db_contexts
    assert state.project_id in state.db_contexts


@pytest.mark.asyncio
async def test_retention_keeps_span_when_payload_delete_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = RetentionState()
    state.spans = [
        {
            "id": str(uuid4()),
            "trace_id": str(uuid4()),
            "started_at": state.expired_started_at,
            "payload_s3_key": f"payloads/{state.project_id}/aa/1.json.gz",
        }
    ]
    state.traces = [
        {"id": state.spans[0]["trace_id"], "started_at": state.expired_started_at}
    ]

    @asynccontextmanager
    async def fake_get_db(project_id: str | None = None):
        yield state.get_db(project_id)

    async def fake_delete_s3_objects(project_id: str, keys: list[str]) -> set[str]:
        return set()

    monkeypatch.setattr(maintenance, "get_db", fake_get_db)
    monkeypatch.setattr(maintenance, "_delete_s3_objects", fake_delete_s3_objects)

    await maintenance.run_data_retention.original_func()

    assert state.deleted_span_ids == set()


@pytest.mark.asyncio
async def test_retention_deletes_only_expired_span_with_duplicate_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = RetentionState()
    duplicate_span_id = str(uuid4())
    expired_trace_id = str(uuid4())
    fresh_trace_id = str(uuid4())
    state.spans = [
        {
            "id": duplicate_span_id,
            "trace_id": expired_trace_id,
            "started_at": state.expired_started_at,
            "payload_s3_key": None,
        },
        {
            "id": duplicate_span_id,
            "trace_id": fresh_trace_id,
            "started_at": state.fresh_started_at,
            "payload_s3_key": None,
        },
    ]
    state.traces = [
        {"id": expired_trace_id, "started_at": state.expired_started_at},
        {"id": fresh_trace_id, "started_at": state.fresh_started_at},
    ]

    @asynccontextmanager
    async def fake_get_db(project_id: str | None = None):
        yield state.get_db(project_id)

    async def fake_delete_s3_objects(project_id: str, keys: list[str]) -> set[str]:
        return set(keys)

    monkeypatch.setattr(maintenance, "get_db", fake_get_db)
    monkeypatch.setattr(maintenance, "_delete_s3_objects", fake_delete_s3_objects)

    await maintenance.run_data_retention.original_func()

    assert state.deleted_span_keys == {(duplicate_span_id, state.expired_started_at)}
    assert state.deleted_traces == 1
