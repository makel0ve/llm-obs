import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SAFE_ARG_KEYS = frozenset({"batch_id", "project_id"})
SENSITIVE_KEY_PARTS = ("api_key", "authorization", "password", "secret", "token")
MAX_SUMMARY_LENGTH = 10_000
MAX_ERROR_LENGTH = 5_000


def summarize_task_args(task_args: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}

    for key, value in task_args.items():
        normalized_key = key.lower()
        if any(part in normalized_key for part in SENSITIVE_KEY_PARTS):
            summary[key] = "[redacted]"
        elif key in SAFE_ARG_KEYS:
            summary[key] = value
        elif key == "spans" and isinstance(value, list):
            summary["span_count"] = len(value)
        elif isinstance(value, str | int | float | bool) or value is None:
            summary[key] = value
        else:
            summary[key] = f"<{type(value).__name__}>"

    return summary


def extract_project_id(task_args: dict[str, Any]) -> str | None:
    project_id = task_args.get("project_id")
    return str(project_id) if project_id else None


async def resolve_org_id(db: AsyncSession, project_id: str | None) -> str | None:
    if not project_id:
        return None

    result = await db.execute(
        text("SELECT org_id FROM projects WHERE id = :project_id"),
        {"project_id": project_id},
    )
    row = result.mappings().one_or_none()
    return str(row["org_id"]) if row else None


async def record_failed_task(
    db: AsyncSession,
    *,
    task_name: str,
    task_args: dict[str, Any],
    error: str,
    attempts: int,
    failed_at: datetime,
) -> None:
    project_id = extract_project_id(task_args)
    org_id = await resolve_org_id(db, project_id)
    args_summary = json.dumps(summarize_task_args(task_args), default=str)[
        :MAX_SUMMARY_LENGTH
    ]

    await db.execute(
        text(
            """
        INSERT INTO failed_tasks (org_id, project_id, task_name, task_args, error,
            attempts, failed_at)
        VALUES (:org_id, :project_id, :task, :args, :error, :attempts, :now)
        """
        ),
        {
            "org_id": org_id,
            "project_id": project_id,
            "task": task_name,
            "args": args_summary,
            "error": error[:MAX_ERROR_LENGTH],
            "attempts": attempts,
            "now": failed_at,
        },
    )
