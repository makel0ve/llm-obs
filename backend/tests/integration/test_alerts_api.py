from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import alerts as alerts_api
from app.api.v1.alerts import delete_rule, resolve_event, update_rule
from app.schemas.alerts import AlertRuleUpdate


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


class FakeResult:
    def __init__(self, row=None):
        self._row = row

    def one_or_none(self):
        return self._row


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDb:
    def __init__(self, *, row=None):
        self.row = row
        self.params = []
        self.statements = []

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        self.params.append(params or {})
        return FakeResult(row=self.row)


def _member(org_id=None):
    return {
        "sub": str(uuid4()),
        "org_id": org_id or str(uuid4()),
        "role": "member",
    }


def _patch_db(monkeypatch, db):
    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(alerts_api, "get_db", fake_get_db)


def _patch_project_access(monkeypatch, calls):
    async def fake_get_project_for_user(project_id, user, required_role="viewer"):
        calls.append(
            {
                "project_id": project_id,
                "user": user,
                "required_role": required_role,
            }
        )
        return {"id": project_id, "org_id": user["org_id"], "project_role": "member"}

    monkeypatch.setattr(alerts_api, "get_project_for_user", fake_get_project_for_user)


@pytest.mark.asyncio
async def test_update_rule_requires_project_member_and_scopes_to_project(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    rule_id = str(uuid4())
    db = FakeDb(row={"id": rule_id})
    access_calls = []
    _patch_db(monkeypatch, db)
    _patch_project_access(monkeypatch, access_calls)

    user = _member(org_id=org_id)
    result = await update_rule(
        rule_id=rule_id,
        project_id=project_id,
        body=AlertRuleUpdate(threshold=500),
        user=user,
    )

    assert result == {"update": True}
    assert access_calls == [
        {
            "project_id": project_id,
            "user": user,
            "required_role": "member",
        }
    ]
    assert "project_id = :project_id" in db.statements[-1]
    assert db.params[-1]["rule_id"] == rule_id
    assert db.params[-1]["project_id"] == project_id


@pytest.mark.asyncio
async def test_update_rule_rejects_foreign_project(monkeypatch):
    db = FakeDb(row=None)
    access_calls = []
    _patch_db(monkeypatch, db)
    _patch_project_access(monkeypatch, access_calls)

    with pytest.raises(HTTPException) as exc_info:
        await update_rule(
            rule_id=str(uuid4()),
            project_id=str(uuid4()),
            body=AlertRuleUpdate(is_active=False),
            user=_member(),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_rule_requires_project_member_and_scopes_to_project(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    rule_id = str(uuid4())
    db = FakeDb(row={"id": rule_id})
    access_calls = []
    _patch_db(monkeypatch, db)
    _patch_project_access(monkeypatch, access_calls)

    user = _member(org_id)
    await delete_rule(rule_id=rule_id, project_id=project_id, user=user)

    assert access_calls == [
        {"project_id": project_id, "user": user, "required_role": "member"}
    ]
    assert "project_id = :project_id" in db.statements[-1]
    assert db.params[-1] == {
        "id": rule_id,
        "project_id": project_id,
    }


@pytest.mark.asyncio
async def test_resolve_event_requires_project_member_and_scopes_to_project(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    event_id = str(uuid4())
    db = FakeDb(row={"id": event_id})
    access_calls = []
    _patch_db(monkeypatch, db)
    _patch_project_access(monkeypatch, access_calls)

    user = _member(org_id)
    result = await resolve_event(event_id=event_id, project_id=project_id, user=user)

    assert result == {"resolved": True}
    assert access_calls == [
        {"project_id": project_id, "user": user, "required_role": "member"}
    ]
    assert "project_id = :project_id" in db.statements[-1]
    assert db.params[-1]["id"] == event_id
    assert db.params[-1]["project_id"] == project_id
