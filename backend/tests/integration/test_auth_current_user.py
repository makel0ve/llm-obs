from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core import auth as auth_module
from app.core.auth import (
    create_access_token,
    get_project_from_token_or_api_key,
    load_current_user_from_token,
)


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self._row


class FakeDb:
    def __init__(
        self,
        *,
        current_user: dict[str, Any] | None,
        project: dict[str, Any] | None = None,
    ) -> None:
        self.current_user = current_user
        self.project = project
        self.params: list[dict[str, Any]] = []

    async def execute(
        self,
        statement: object,
        params: dict[str, Any] | None = None,
    ) -> FakeResult:
        sql = str(statement)
        self.params.append(params or {})

        if "FROM users" in sql and "is_active = true" in sql:
            return FakeResult(self.current_user)

        if "FROM projects p" in sql and "LEFT JOIN project_memberships" in sql:
            return FakeResult(self.project)

        raise AssertionError(f"Unexpected SQL: {sql}")


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


def _patch_db(monkeypatch: pytest.MonkeyPatch, db: FakeDb) -> None:
    @asynccontextmanager
    async def fake_get_db() -> AsyncIterator[FakeDb]:
        yield db

    monkeypatch.setattr(auth_module, "get_db", fake_get_db)


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.asyncio
async def test_deleted_or_disabled_user_token_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(str(uuid4()), str(uuid4()), "admin")
    _patch_db(monkeypatch, FakeDb(current_user=None))

    with pytest.raises(HTTPException) as exc_info:
        await load_current_user_from_token(token)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_uses_latest_db_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = str(uuid4())
    org_id = str(uuid4())
    token = create_access_token(user_id, org_id, "admin")
    _patch_db(
        monkeypatch,
        FakeDb(
            current_user={
                "id": user_id,
                "org_id": org_id,
                "role": "viewer",
                "is_platform_admin": False,
            }
        ),
    )

    user = await load_current_user_from_token(token)

    assert user == {
        "sub": user_id,
        "org_id": org_id,
        "role": "viewer",
        "is_platform_admin": False,
    }


@pytest.mark.asyncio
async def test_current_user_uses_latest_platform_admin_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = str(uuid4())
    org_id = str(uuid4())
    token = create_access_token(user_id, org_id, "admin")
    _patch_db(
        monkeypatch,
        FakeDb(
            current_user={
                "id": user_id,
                "org_id": org_id,
                "role": "admin",
                "is_platform_admin": True,
            }
        ),
    )

    user = await load_current_user_from_token(token)

    assert user["role"] == "admin"
    assert user["is_platform_admin"] is True


@pytest.mark.asyncio
async def test_project_access_uses_current_role_not_stale_jwt_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = str(uuid4())
    org_id = str(uuid4())
    project_id = str(uuid4())
    token = create_access_token(user_id, org_id, "admin")
    db = FakeDb(
        current_user={
            "id": user_id,
            "org_id": org_id,
            "role": "viewer",
            "is_platform_admin": False,
        },
        project={
            "id": project_id,
            "org_id": org_id,
            "name": "Private project",
            "project_role": None,
        },
    )
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await get_project_from_token_or_api_key(
            creds=_credentials(token),
            x_api_key=None,
            project_id=project_id,
        )

    assert exc_info.value.status_code == 403
