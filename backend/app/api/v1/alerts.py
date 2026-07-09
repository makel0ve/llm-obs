import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.rbac import require_member
from app.schemas.alerts import AlertRuleCreate, AlertRuleUpdate

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])
ALLOWED_UPDATE_FIELDS = {
    "is_active",
    "threshold",
    "notify_slack_webhook",
    "notify_email",
}


@router.get("/rules")
async def list_rules(project_id: str, user=Depends(get_current_user)):
    async with get_db() as db:
        project = await db.execute(
            text("SELECT id FROM projects WHERE id = :pid AND org_id = :org"),
            {"pid": project_id, "org": user["org_id"]},
        )
        if not project.one_or_none():
            raise HTTPException(404, "Project not found")

        result = await db.execute(
            text(
                "SELECT * FROM alert_rules WHERE project_id = :pid "
                "ORDER BY created_at DESC"
            ),
            {"pid": project_id},
        )

        return result.mappings().all()


@router.post("/rules", status_code=201)
async def create_rule(body: AlertRuleCreate, user=Depends(get_current_user)):
    require_member(user)

    async with get_db() as db:
        async with db.begin():
            project = await db.execute(
                text("SELECT id FROM projects WHERE id = :pid AND org_id = :org"),
                {"pid": body.project_id, "org": user["org_id"]},
            )
            if not project.one_or_none():
                raise HTTPException(404, "Project not found")

            rule_id = str(uuid.uuid4())
            await db.execute(
                text(
                    """
                INSERT INTO alert_rules
                (id, project_id, name, metric, condition, threshold,
                window_minutes, cooldown_minutes, notify_slack_webhook,
                notify_email, is_active)
                VALUES (:id, :project_id, :name, :metric, :condition, :threshold,
                :window_minutes, :cooldown_minutes, :slack, :email, true)
                """
                ),
                {
                    "id": rule_id,
                    "project_id": body.project_id,
                    "name": body.name,
                    "metric": body.metric,
                    "condition": body.condition,
                    "threshold": body.threshold,
                    "window_minutes": body.window_minutes,
                    "cooldown_minutes": body.cooldown_minutes,
                    "slack": body.notify_slack_webhook,
                    "email": body.notify_email,
                },
            )

    return {"id": rule_id}


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: str, body: AlertRuleUpdate, user=Depends(get_current_user)
):
    require_member(user)

    updates = {
        k: v
        for k, v in body.model_dump().items()
        if v is not None and k in ALLOWED_UPDATE_FIELDS
    }
    if not updates:
        raise HTTPException(400, "No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    async with get_db() as db:
        async with db.begin():
            result = await db.execute(
                text(
                    f"""
                UPDATE alert_rules SET {set_clause}
                WHERE id = :rule_id AND project_id IN
                (SELECT id FROM projects WHERE org_id = :org) RETURNING id
                """  # nosec B608
                ),
                {**updates, "rule_id": rule_id, "org": user["org_id"]},
            )
            if not result.one_or_none():
                raise HTTPException(404, "Rule not found")

    return {"update": True}


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, user=Depends(get_current_user)):
    require_member(user)

    async with get_db() as db:
        async with db.begin():
            result = await db.execute(
                text(
                    """
                DELETE FROM alert_rules WHERE id = :id AND project_id IN
                (SELECT id FROM projects WHERE org_id = :org) RETURNING id
                """
                ),
                {"id": rule_id, "org": user["org_id"]},
            )
            if not result.one_or_none():
                raise HTTPException(404, "Rule not found")


@router.get("/events")
async def list_events(project_id: str, user=Depends(get_current_user)):
    async with get_db() as db:
        project = await db.execute(
            text("SELECT id FROM projects WHERE id = :pid AND org_id = :org"),
            {"pid": project_id, "org": user["org_id"]},
        )
        if not project.one_or_none():
            raise HTTPException(404, "Project not found")

        result = await db.execute(
            text(
                """
            SELECT ae.* FROM alert_events ae
            JOIN alert_rules ar ON ae.rule_id = ar.id
            WHERE ar.project_id = :pid
            ORDER BY ae.triggered_at DESC
            LIMIT 100
            """
            ),
            {"pid": project_id},
        )

        return result.mappings().all()


@router.post("/events/{event_id}/resolve")
async def resolve_event(event_id: str, user=Depends(get_current_user)):
    require_member(user)

    async with get_db() as db:
        async with db.begin():
            result = await db.execute(
                text(
                    """
                UPDATE alert_events SET resolved_at = :now
                WHERE id = :id AND rule_id IN (
                    SELECT id FROM alert_rules WHERE project_id IN (
                        SELECT id FROM projects WHERE org_id = :org
                    )
                ) RETURNING id
                """
                ),
                {"id": event_id, "org": user["org_id"], "now": datetime.now(UTC)},
            )
            if not result.one_or_none():
                raise HTTPException(404, "Event not found")

    return {"resolved": True}
