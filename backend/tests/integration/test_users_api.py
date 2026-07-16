import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import alerts as alerts_api
from app.api.v1 import projects as projects_api
from app.api.v1 import users as users_api
from app.api.v1.alerts import create_rule
from app.api.v1.projects import rotate_api_key, update_settings
from app.api.v1.users import (
    accept_invite,
    create_invite,
    delete_user,
    list_users,
    update_user_role,
)
from app.schemas.alerts import AlertRuleCreate
from app.schemas.projects import ProjectSettingsUpdate
from app.schemas.users import UserInviteAccept, UserInviteCreate, UserRoleUpdate


class FakeResult:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def one(self):
        if self._row is None:
            raise AssertionError("expected row")
        return self._row

    def one_or_none(self):
        return self._row


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDb:
    def __init__(
        self,
        *,
        rows=None,
        existing_email=False,
        target_user=None,
        admin_count=2,
        project_ids=None,
    ):
        self.rows = rows or []
        self.existing_email = existing_email
        self.target_user = target_user
        self.admin_count = admin_count
        self.project_ids = project_ids
        self.params = []

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.params.append(params or {})

        if "SELECT id, email, role, is_active, created_at" in sql:
            return FakeResult(rows=self.rows)

        if "SELECT 1 FROM users WHERE email" in sql:
            return FakeResult(row={"exists": 1} if self.existing_email else None)

        if "SELECT id" in sql and "FROM projects" in sql and "ANY" in sql:
            project_ids = self.project_ids
            if project_ids is None:
                project_ids = params["project_ids"]
            return FakeResult(rows=[{"id": project_id} for project_id in project_ids])

        if "INSERT INTO organization_invites" in sql:
            return FakeResult(
                row={
                    "id": params["id"],
                    "email": params["email"],
                    "role": params["role"],
                    "project_assignments": json.loads(
                        params.get("project_assignments", "[]")
                    ),
                    "expires_at": params["expires_at"],
                }
            )

        if "FROM organization_invites" in sql:
            return FakeResult(row=self.target_user)

        if "INSERT INTO users" in sql:
            return FakeResult()

        if "INSERT INTO project_memberships" in sql:
            return FakeResult()

        if "UPDATE organization_invites" in sql:
            return FakeResult(row={"id": params["id"]})

        if "SELECT id FROM projects" in sql:
            return FakeResult(row={"id": str(uuid4())})

        if "SELECT id, email, role" in sql:
            return FakeResult(row=self.target_user)

        if "SELECT count(*) AS count" in sql:
            return FakeResult(row={"count": self.admin_count})

        if "UPDATE users" in sql:
            return FakeResult(
                row=_user_row(params["id"], "member@example.com", params["role"])
            )

        if "DELETE FROM users" in sql:
            return FakeResult(row={"id": params["id"]})

        return FakeResult()


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


def _admin(org_id=None, user_id=None):
    return {
        "sub": user_id or str(uuid4()),
        "org_id": org_id or str(uuid4()),
        "role": "admin",
    }


def _user(role="member", org_id=None):
    return {
        "sub": str(uuid4()),
        "org_id": org_id or str(uuid4()),
        "role": role,
    }


def _user_row(user_id, email, role):
    return {
        "id": user_id,
        "email": email,
        "role": role,
        "is_active": True,
        "created_at": datetime.now(UTC),
    }


def _patch_db(monkeypatch, db):
    @asynccontextmanager
    async def fake_get_db():
        yield db

    monkeypatch.setattr(users_api, "get_db", fake_get_db)


async def _noop_log_audit(**kwargs):
    return None


@pytest.mark.asyncio
async def test_list_users_requires_admin():
    with pytest.raises(HTTPException) as exc_info:
        await list_users(user=_user(role="member"))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_users_scopes_to_admin_org(monkeypatch):
    org_id = str(uuid4())
    db = FakeDb(rows=[_user_row(str(uuid4()), "admin@example.com", "admin")])
    _patch_db(monkeypatch, db)

    result = await list_users(user=_admin(org_id=org_id))

    assert result[0]["email"] == "admin@example.com"
    assert db.params[-1] == {"org": org_id}


@pytest.mark.asyncio
async def test_create_invite_uses_admin_org_and_returns_token(monkeypatch):
    org_id = str(uuid4())
    db = FakeDb()
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(users_api.secrets, "token_urlsafe", lambda size: "raw-token")
    audit_events = []

    async def fake_log_audit(**kwargs):
        audit_events.append(kwargs)

    monkeypatch.setattr(users_api, "log_audit", fake_log_audit)

    result = await create_invite(
        UserInviteCreate(email="viewer@example.com", role="viewer"),
        user=_admin(org_id=org_id),
    )

    assert result["role"] == "viewer"
    assert result["invite_token"] == "raw-token"
    insert_params = db.params[-1]
    assert insert_params["org"] == org_id
    assert insert_params["token_hash"] == users_api.hash_invite_token("raw-token")
    assert audit_events == [
        {
            "org_id": org_id,
            "user_id": audit_events[0]["user_id"],
            "action": "user.invite.create",
            "resource_id": result["id"],
            "metadata": {
                "email": "viewer@example.com",
                "role": "viewer",
                "project_assignment_count": 0,
            },
        }
    ]


@pytest.mark.asyncio
async def test_create_invite_stores_project_assignments(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    db = FakeDb(project_ids=[project_id])
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(users_api.secrets, "token_urlsafe", lambda size: "raw-token")
    audit_events = []

    async def fake_log_audit(**kwargs):
        audit_events.append(kwargs)

    monkeypatch.setattr(users_api, "log_audit", fake_log_audit)

    result = await create_invite(
        UserInviteCreate(
            email="viewer@example.com",
            role="viewer",
            project_assignments=[{"project_id": project_id, "role": "viewer"}],
        ),
        user=_admin(org_id=org_id),
    )

    assert result["project_assignments"] == [
        {"project_id": project_id, "role": "viewer"}
    ]
    project_lookup = next(params for params in db.params if "project_ids" in params)
    assert project_lookup == {"org": org_id, "project_ids": [project_id]}
    assert audit_events[0]["metadata"]["project_assignment_count"] == 1


@pytest.mark.asyncio
async def test_create_invite_rejects_foreign_project_assignment(monkeypatch):
    project_id = str(uuid4())
    db = FakeDb(project_ids=[])
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(users_api, "log_audit", _noop_log_audit)

    with pytest.raises(HTTPException) as exc_info:
        await create_invite(
            UserInviteCreate(
                email="viewer@example.com",
                project_assignments=[{"project_id": project_id, "role": "viewer"}],
            ),
            user=_admin(),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_invite_rejects_duplicate_email(monkeypatch):
    db = FakeDb(existing_email=True)
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(users_api, "log_audit", _noop_log_audit)

    with pytest.raises(HTTPException) as exc_info:
        await create_invite(
            UserInviteCreate(email="taken@example.com"),
            user=_admin(),
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_accept_invite_hashes_password_and_returns_token(monkeypatch):
    org_id = str(uuid4())
    invite = {
        "id": str(uuid4()),
        "org_id": org_id,
        "email": "member@example.com",
        "role": "member",
        "project_assignments": [],
        "expires_at": datetime.now(UTC).replace(year=datetime.now(UTC).year + 1),
    }
    db = FakeDb(target_user=invite)
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(users_api, "log_audit", _noop_log_audit)
    monkeypatch.setattr(
        users_api, "hash_password", lambda password: f"hashed:{password}"
    )
    monkeypatch.setattr(
        users_api,
        "create_access_token",
        lambda user_id, org_id, role: f"token:{org_id}:{role}",
    )

    result = await accept_invite(
        UserInviteAccept(
            token="raw-token-value-that-is-long-enough",
            password="qwerty123456",
        )
    )

    assert result["access_token"] == f"token:{org_id}:member"
    insert_params = next(params for params in db.params if "password_hash" in params)
    assert insert_params["password_hash"] == "hashed:qwerty123456"


@pytest.mark.asyncio
async def test_accept_invite_creates_project_memberships(monkeypatch):
    org_id = str(uuid4())
    project_id = str(uuid4())
    invite = {
        "id": str(uuid4()),
        "org_id": org_id,
        "email": "member@example.com",
        "role": "member",
        "project_assignments": [{"project_id": project_id, "role": "member"}],
        "expires_at": datetime.now(UTC).replace(year=datetime.now(UTC).year + 1),
    }
    db = FakeDb(target_user=invite)
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(users_api, "log_audit", _noop_log_audit)
    monkeypatch.setattr(users_api, "hash_password", lambda password: "hashed")
    monkeypatch.setattr(users_api, "create_access_token", lambda *args: "token")

    result = await accept_invite(
        UserInviteAccept(
            token="raw-token-value-that-is-long-enough",
            password="qwerty123456",
        )
    )

    membership_params = next(
        params for params in db.params if params.get("project_id") == project_id
    )
    assert membership_params["role"] == "member"
    assert result["project_id"] == project_id


@pytest.mark.asyncio
async def test_accept_invite_rejects_expired_invite(monkeypatch):
    invite = {
        "id": str(uuid4()),
        "org_id": str(uuid4()),
        "email": "member@example.com",
        "role": "member",
        "project_assignments": [],
        "expires_at": datetime.now(UTC).replace(year=datetime.now(UTC).year - 1),
    }
    db = FakeDb(target_user=invite)
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(users_api, "log_audit", _noop_log_audit)

    with pytest.raises(HTTPException) as exc_info:
        await accept_invite(
            UserInviteAccept(
                token="raw-token-value-that-is-long-enough",
                password="qwerty123456",
            )
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_update_user_role_keeps_at_least_one_admin(monkeypatch):
    admin_id = str(uuid4())
    db = FakeDb(
        target_user={"id": admin_id, "email": "admin@example.com", "role": "admin"},
        admin_count=1,
    )
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await update_user_role(
            admin_id,
            UserRoleUpdate(role="member"),
            user=_admin(user_id=str(uuid4())),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_update_user_role_rejects_self_demotion():
    admin_id = str(uuid4())

    with pytest.raises(HTTPException) as exc_info:
        await update_user_role(
            admin_id,
            UserRoleUpdate(role="viewer"),
            user=_admin(user_id=admin_id),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_user_rejects_self_delete():
    admin_id = str(uuid4())

    with pytest.raises(HTTPException) as exc_info:
        await delete_user(admin_id, user=_admin(user_id=admin_id))

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_user_keeps_at_least_one_admin(monkeypatch):
    admin_id = str(uuid4())
    db = FakeDb(
        target_user={"id": admin_id, "email": "admin@example.com", "role": "admin"},
        admin_count=1,
    )
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await delete_user(admin_id, user=_admin(user_id=str(uuid4())))

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_user_scopes_to_admin_org(monkeypatch):
    org_id = str(uuid4())
    member_id = str(uuid4())
    db = FakeDb(
        target_user={"id": member_id, "email": "member@example.com", "role": "member"}
    )
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(users_api, "log_audit", _noop_log_audit)

    await delete_user(member_id, user=_admin(org_id=org_id))

    assert db.params[-1] == {"id": member_id, "org": org_id}


@pytest.mark.asyncio
async def test_project_settings_requires_admin_before_db():
    with pytest.raises(HTTPException) as exc_info:
        await update_settings(
            str(uuid4()),
            ProjectSettingsUpdate(retention_days=30),
            user=_user(role="member"),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_project_key_rotation_requires_admin_before_redis(monkeypatch):
    async def fail_get_redis():
        raise AssertionError("redis should not be used")

    monkeypatch.setattr(projects_api, "get_redis", fail_get_redis)

    with pytest.raises(HTTPException) as exc_info:
        await rotate_api_key(str(uuid4()), user=_user(role="member"))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_create_alert_rule(monkeypatch):
    @asynccontextmanager
    async def fail_get_db():
        raise AssertionError("db should not be used")
        yield

    async def deny_project_access(project_id, user, required_role="viewer"):
        raise HTTPException(status_code=403, detail="Project access denied")

    monkeypatch.setattr(alerts_api, "get_db", fail_get_db)
    monkeypatch.setattr(alerts_api, "get_project_for_user", deny_project_access)

    with pytest.raises(HTTPException) as exc_info:
        await create_rule(
            AlertRuleCreate(
                project_id=str(uuid4()),
                name="latency",
                metric="latency_p95",
                condition="gt",
                threshold=500,
                window_minutes=5,
                cooldown_minutes=15,
                notify_email="alerts@example.com",
            ),
            user=_user(role="viewer"),
        )

    assert exc_info.value.status_code == 403
