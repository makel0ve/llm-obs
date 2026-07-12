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


@pytest.mark.asyncio
async def test_update_rule_scopes_to_project_and_org(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    rule_id = str(uuid4())
    db = FakeDb(row={"id": rule_id})
    _patch_db(monkeypatch, db)

    result = await update_rule(
        rule_id=rule_id,
        project_id=project_id,
        body=AlertRuleUpdate(threshold=500),
        user=_member(org_id=org_id),
    )

    assert result == {"update": True}
    assert "project_id = :project_id" in db.statements[-1]
    assert db.params[-1]["rule_id"] == rule_id
    assert db.params[-1]["project_id"] == project_id
    assert db.params[-1]["org"] == org_id


@pytest.mark.asyncio
async def test_update_rule_rejects_foreign_project(monkeypatch):
    db = FakeDb(row=None)
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await update_rule(
            rule_id=str(uuid4()),
            project_id=str(uuid4()),
            body=AlertRuleUpdate(is_active=False),
            user=_member(),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_rule_scopes_to_project_and_org(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    rule_id = str(uuid4())
    db = FakeDb(row={"id": rule_id})
    _patch_db(monkeypatch, db)

    await delete_rule(rule_id=rule_id, project_id=project_id, user=_member(org_id))

    assert "project_id = :project_id" in db.statements[-1]
    assert db.params[-1] == {
        "id": rule_id,
        "project_id": project_id,
        "org": org_id,
    }


@pytest.mark.asyncio
async def test_resolve_event_scopes_to_project_and_org(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    event_id = str(uuid4())
    db = FakeDb(row={"id": event_id})
    _patch_db(monkeypatch, db)

    result = await resolve_event(
        event_id=event_id, project_id=project_id, user=_member(org_id)
    )

    assert result == {"resolved": True}
    assert "project_id = :project_id" in db.statements[-1]
    assert db.params[-1]["id"] == event_id
    assert db.params[-1]["project_id"] == project_id
    assert db.params[-1]["org"] == org_id
