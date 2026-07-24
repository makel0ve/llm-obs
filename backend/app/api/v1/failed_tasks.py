import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.rbac import require_admin
from app.schemas.failed_tasks import (
    FailedTaskResolveResponse,
    FailedTaskResponse,
    FailedTaskRetryResponse,
)
from app.workers.process_span import process_span_batch

router = APIRouter(prefix="/v1/failed-tasks", tags=["failed-tasks"])


def _is_process_span_batch_task(task_name: str) -> bool:
    return task_name == "process_span_batch" or task_name.endswith(
        ":process_span_batch"
    )


def _serialize_failed_task(row) -> dict:
    task = dict(row)
    if task.get("project_id") is not None:
        task["project_id"] = str(task["project_id"])
    if isinstance(task.get("task_args"), str):
        try:
            task["task_args"] = json.loads(task["task_args"])
        except json.JSONDecodeError:
            task["task_args"] = {"summary": task["task_args"]}
    return task


@router.get("", response_model=list[FailedTaskResponse])
async def list_failed_tasks(
    project_id: str | None = None,
    include_resolved: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(get_current_user),
):
    require_admin(user)

    async with get_db() as db:
        if project_id:
            project = await db.execute(
                text("SELECT id FROM projects WHERE id = :pid AND org_id = :org"),
                {"pid": project_id, "org": user["org_id"]},
            )
            if not project.one_or_none():
                raise HTTPException(404, "Project not found")

        result = await db.execute(
            text(
                """
            SELECT id, task_name, project_id, task_args, error, attempts,
                failed_at, resolved
            FROM failed_tasks
            WHERE org_id = :org
              AND (
                CAST(:project_id AS uuid) IS NULL
                OR project_id = CAST(:project_id AS uuid)
              )
              AND (:include_resolved OR resolved = false)
            ORDER BY failed_at DESC
            LIMIT :limit
            """
            ),
            {
                "org": user["org_id"],
                "project_id": project_id,
                "include_resolved": include_resolved,
                "limit": limit,
            },
        )

    return [_serialize_failed_task(row) for row in result.mappings().all()]


@router.post("/{task_id}/resolve", response_model=FailedTaskResolveResponse)
async def resolve_failed_task(task_id: int, user=Depends(get_current_user)):
    require_admin(user)

    async with get_db() as db:
        result = await db.execute(
            text(
                """
            UPDATE failed_tasks
            SET resolved = true
            WHERE id = :task_id AND org_id = :org
            RETURNING id
            """
            ),
            {
                "task_id": task_id,
                "org": user["org_id"],
            },
        )
        if not result.one_or_none():
            raise HTTPException(404, "Failed task not found")

        await db.commit()

    return FailedTaskResolveResponse(resolved=True)


@router.post("/{task_id}/retry", response_model=FailedTaskRetryResponse)
async def retry_failed_task(task_id: int, user=Depends(get_current_user)):
    require_admin(user)

    async with get_db() as db:
        current = await db.execute(
            text(
                """
            SELECT id, task_name, project_id, task_args, resolved
            FROM failed_tasks
            WHERE id = :task_id AND org_id = :org
            """
            ),
            {"task_id": task_id, "org": user["org_id"]},
        )
        task = current.mappings().one_or_none()
        if not task:
            raise HTTPException(404, "Failed task not found")
        if task["resolved"]:
            raise HTTPException(409, "Failed task is already resolved")
        if not _is_process_span_batch_task(str(task["task_name"])):
            raise HTTPException(409, "Failed task type cannot be retried")

        try:
            task_args = json.loads(task["task_args"] or "{}")
        except json.JSONDecodeError:
            raise HTTPException(409, "Failed task arguments are not retryable")

        batch_id = task_args.get("batch_id")
        project_id = task_args.get("project_id") or (
            str(task["project_id"]) if task["project_id"] else None
        )
        spans = task_args.get("spans")
        if not batch_id or not project_id or not isinstance(spans, list):
            raise HTTPException(409, "Failed task payload is not available for retry")

        project = await db.execute(
            text("SELECT id FROM projects WHERE id = :pid AND org_id = :org"),
            {"pid": project_id, "org": user["org_id"]},
        )
        if not project.one_or_none():
            raise HTTPException(404, "Project not found")

        await process_span_batch.kiq(
            batch_id=str(batch_id),
            project_id=str(project_id),
            spans=spans,
        )
        result = await db.execute(
            text(
                """
            UPDATE failed_tasks
            SET resolved = true
            WHERE id = :task_id AND org_id = :org
            RETURNING id
            """
            ),
            {"task_id": task_id, "org": user["org_id"]},
        )
        if not result.one_or_none():
            raise HTTPException(404, "Failed task not found")

        await db.commit()

    return FailedTaskRetryResponse(retried=True)
