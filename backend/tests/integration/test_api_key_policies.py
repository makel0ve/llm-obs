from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import projects as projects_api
from app.api.v1.projects import create_api_key, list_api_keys, revoke_api_key
from app.core import auth as auth_module
from app.core.auth import get_project_from_api_key
from app.schemas.projects import ProjectApiKeyCreate


class FakeResult:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def one_or_none(self):
        return self._row

    def one(self):
        if self._row is None:
            raise AssertionError("expected row")
        return self._row


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDb:
    def __init__(self, *, project_row=None, api_key_rows=None, api_key_row=None):
        self.project_row = project_row or {"id": str(uuid4())}
        self.api_key_rows = api_key_rows or []
        self.api_key_row = api_key_row
        self.params = []
        self.committed = False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.params.append(params or {})

        if "FROM projects WHERE id" in sql:
            return FakeResult(row=self.project_row)

        if "FROM project_api_keys" in sql and "ORDER BY created_at" in sql:
            return FakeResult(rows=self.api_key_rows)

        if "INSERT INTO project_api_keys" in sql:
            return FakeResult(row=_api_key_record(params))

        if "UPDATE project_api_keys" in sql and "RETURNING key_hash" in sql:
            return FakeResult(row=self.api_key_row or {"key_hash": "abc"})

        if "SELECT p.id, p.org_id" in sql:
            return FakeResult(row=self.api_key_row)

        return FakeResult()

    async def commit(self):
        self.committed = True


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.deleted = []

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        self.values[key] = value

    async def delete(self, key):
        self.deleted.append(key)


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


def _admin(org_id=None):
    return {"sub": str(uuid4()), "org_id": org_id or str(uuid4()), "role": "admin"}


def _api_key_record(params):
    return {
        "id": params.get("id", str(uuid4())),
        "name": params["name"],
        "description": params["description"],
        "scope": params["scope"],
        "is_active": True,
        "created_at": datetime.now(UTC),
        "last_used_at": None,
        "revoked_at": None,
    }


def _patch_project_deps(monkeypatch, db, redis=None):
    @asynccontextmanager
    async def fake_get_db():
        yield db

    async def fake_get_redis():
        return redis or FakeRedis()

    async def fake_log_audit(**kwargs):
        return None

    monkeypatch.setattr(projects_api, "get_db", fake_get_db)
    monkeypatch.setattr(projects_api, "get_redis", fake_get_redis)
    monkeypatch.setattr(projects_api, "log_audit", fake_log_audit)


def _patch_auth_deps(monkeypatch, db, redis):
    @asynccontextmanager
    async def fake_get_db():
        yield db

    async def fake_get_redis():
        return redis

    monkeypatch.setattr(auth_module, "get_db", fake_get_db)
    monkeypatch.setattr(auth_module, "get_redis", fake_get_redis)


@pytest.mark.asyncio
async def test_create_api_key_returns_raw_key_once(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    db = FakeDb(project_row={"id": project_id})
    _patch_project_deps(monkeypatch, db)
    monkeypatch.setattr(projects_api.secrets, "token_urlsafe", lambda size: "raw-token")

    result = await create_api_key(
        project_id,
        ProjectApiKeyCreate(name="CI ingest", description="pipeline", scope="ingest"),
        user=_admin(org_id=org_id),
    )

    assert result["api_key"] == "llmobs_raw-token"
    assert result["scope"] == "ingest"
    assert db.params[-1]["project_id"] == project_id
    assert "key_hash" in db.params[-1]


@pytest.mark.asyncio
async def test_list_api_keys_scopes_to_project_org(monkeypatch):
    project_id = str(uuid4())
    row = _api_key_record(
        {"id": str(uuid4()), "name": "Read", "description": None, "scope": "read"}
    )
    db = FakeDb(api_key_rows=[row])
    _patch_project_deps(monkeypatch, db)

    result = await list_api_keys(project_id, user=_admin())

    assert result == [row]
    assert db.params[-1] == {"project_id": project_id}


@pytest.mark.asyncio
async def test_revoke_api_key_invalidates_cache(monkeypatch):
    project_id = str(uuid4())
    key_id = str(uuid4())
    redis = FakeRedis()
    db = FakeDb(api_key_row={"key_hash": "deadbeef"})
    _patch_project_deps(monkeypatch, db, redis=redis)

    result = await revoke_api_key(project_id, key_id, user=_admin())

    assert result == {"revoked": True}
    assert redis.deleted == ["apikey:deadbeef"]


@pytest.mark.asyncio
async def test_read_key_cannot_ingest(monkeypatch):
    db = FakeDb(
        api_key_row={
            "id": str(uuid4()),
            "org_id": str(uuid4()),
            "name": "Project",
            "scope": "read",
            "api_key_id": str(uuid4()),
            "legacy": False,
        }
    )
    _patch_auth_deps(monkeypatch, db, FakeRedis())

    with pytest.raises(HTTPException) as exc_info:
        await get_project_from_api_key(x_api_key="llmobs_read", required_scope="ingest")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_read_write_key_can_read_and_ingest(monkeypatch):
    db = FakeDb(
        api_key_row={
            "id": str(uuid4()),
            "org_id": str(uuid4()),
            "name": "Project",
            "scope": "read_write",
            "api_key_id": str(uuid4()),
            "legacy": False,
        }
    )
    _patch_auth_deps(monkeypatch, db, FakeRedis())

    result = await get_project_from_api_key(
        x_api_key="llmobs_read_write", required_scope="ingest"
    )

    assert result["scope"] == "read_write"
    assert db.committed is True
