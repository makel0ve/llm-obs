from contextlib import asynccontextmanager
from typing import TypedDict
from uuid import uuid4

import pytest

from app.workers import maintenance


class RetentionSpan(TypedDict):
    id: str
    payload_s3_key: str | None


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

        if "SELECT id, payload_s3_key" in sql:
            assert self._project_context == self._state.project_id
            batch = [
                span
                for span in self._state.spans
                if span["id"] not in self._state.deleted_span_ids
            ][: int(params["limit"])]
            return FakeResult([dict(span) for span in batch])

        if "DELETE FROM spans" in sql:
            assert self._project_context == self._state.project_id
            span_ids = {str(span_id) for span_id in params["span_ids"]}
            self._state.deleted_span_ids.update(span_ids)
            return FakeResult(rowcount=len(span_ids))

        if "DELETE FROM traces" in sql:
            assert self._project_context == self._state.project_id
            self._state.deleted_traces += 1
            return FakeResult(rowcount=1)

        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self) -> None:
        return None


class RetentionState:
    def __init__(self) -> None:
        self.project_id = str(uuid4())
        self.retention_days = 7
        self.spans: list[RetentionSpan] = [
            {
                "id": str(uuid4()),
                "payload_s3_key": f"payloads/{self.project_id}/aa/1.json.gz",
            },
            {"id": str(uuid4()), "payload_s3_key": None},
        ]
        self.deleted_span_ids: set[str] = set()
        self.deleted_traces = 0
        self.db_contexts: list[str | None] = []
        self.deleted_payload_keys: list[str] = []

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
            "payload_s3_key": f"payloads/{state.project_id}/aa/1.json.gz",
        }
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
