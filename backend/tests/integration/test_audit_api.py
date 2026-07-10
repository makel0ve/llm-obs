import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import audit as audit_api
from app.api.v1.audit import list_audit_events, parse_metadata


class FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.params = []

    async def execute(self, statement, params=None):
        self.params.append(params or {})
        return FakeResult(rows=self.rows)


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


def _user(role="admin", org_id=None):
    return {
        "sub": str(uuid4()),
        "org_id": org_id or str(uuid4()),
        "role": role,
    }


def test_parse_metadata_accepts_json_strings():
    assert parse_metadata('{"role": "viewer"}') == {"role": "viewer"}
    assert parse_metadata("not-json") == {}
    assert parse_metadata(["not", "dict"]) == {}


@pytest.mark.asyncio
async def test_list_audit_events_requires_admin():
    with pytest.raises(HTTPException) as exc_info:
        await list_audit_events(user=_user(role="member"))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_audit_events_filters_and_paginates(monkeypatch):
    org_id = str(uuid4())
    actor_id = str(uuid4())
    rows = [
        {
            "id": 12,
            "action": "user.role.update",
            "user_id": actor_id,
            "user_email": "admin@example.com",
            "resource_id": str(uuid4()),
            "metadata": json.dumps({"old_role": "member", "new_role": "admin"}),
            "created_at": datetime.now(UTC),
        },
        {
            "id": 11,
            "action": "user.invite.create",
            "user_id": actor_id,
            "user_email": "admin@example.com",
            "resource_id": str(uuid4()),
            "metadata": {},
            "created_at": datetime.now(UTC),
        },
    ]
    db = FakeDb(rows=rows)

    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(audit_api, "get_db", fake_get_db)

    result = await list_audit_events(
        action="user.role.update",
        user_id=actor_id,
        from_dt=None,
        to_dt=None,
        cursor=20,
        page_size=1,
        user=_user(org_id=org_id),
    )

    assert len(result.events) == 1
    assert result.events[0].action == "user.role.update"
    assert result.events[0].metadata == {"old_role": "member", "new_role": "admin"}
    assert result.next_cursor == "12"
    assert db.params[-1] == {
        "org": org_id,
        "action": "%user.role.update%",
        "user_id": actor_id,
        "from_dt": None,
        "to_dt": None,
        "cursor": 20,
        "limit": 2,
    }


@pytest.mark.asyncio
async def test_list_audit_events_uses_partial_action_search(monkeypatch):
    db = FakeDb()

    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(audit_api, "get_db", fake_get_db)

    await list_audit_events(
        action="api_key",
        user_id=None,
        from_dt=None,
        to_dt=None,
        cursor=None,
        page_size=50,
        user=_user(),
    )

    assert db.params[-1]["action"] == "%api_key%"
