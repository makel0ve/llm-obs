from collections.abc import Mapping
from typing import Literal, TypeGuard

from fastapi import HTTPException

RoleName = Literal["viewer", "member", "admin"]

ROLE_LEVELS: dict[RoleName, int] = {
    "viewer": 0,
    "member": 1,
    "admin": 2,
}


def is_role_name(value: object) -> TypeGuard[RoleName]:
    return value in ROLE_LEVELS


def require_role(user: Mapping[str, object], minimum_role: RoleName) -> None:
    role = user.get("role")
    current_level = ROLE_LEVELS[role] if is_role_name(role) else -1
    required_level = ROLE_LEVELS[minimum_role]

    if current_level < required_level:
        raise HTTPException(
            status_code=403,
            detail=f"{minimum_role.capitalize()} role required",
        )


def require_admin(user: Mapping[str, object]) -> None:
    require_role(user, "admin")


def require_member(user: Mapping[str, object]) -> None:
    require_role(user, "member")
