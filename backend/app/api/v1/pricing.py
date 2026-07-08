from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.redis import get_redis
from app.schemas.pricing import (
    PricingCreate,
    PricingEndDate,
    PricingRecord,
    PricingUpdate,
)

router = APIRouter(prefix="/v1/pricing", tags=["pricing"])


def require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def normalize_name(value: str) -> str:
    return value.strip().lower()


async def invalidate_pricing_cache(provider: str, model: str) -> None:
    redis = await get_redis()
    await redis.delete(f"pricing:{provider}:{model}")


@router.get("", response_model=list[PricingRecord])
async def list_pricing(
    provider: str | None = None,
    model: str | None = None,
    include_expired: bool = True,
    user=Depends(get_current_user),
):
    require_admin(user)

    provider_filter = normalize_name(provider) if provider else None
    model_filter = model.strip() if model else None

    async with get_db() as db:
        result = await db.execute(
            text(
                """
            SELECT id, provider, model, input_cost_per_1k_tokens,
                output_cost_per_1k_tokens, valid_from, valid_to
            FROM model_pricing
            WHERE (
                CAST(:provider AS text) IS NULL
                OR provider = CAST(:provider AS text)
              )
              AND (
                CAST(:model AS text) IS NULL
                OR model ILIKE CAST(:model_like AS text)
              )
              AND (:include_expired OR valid_to IS NULL OR valid_to > :now)
            ORDER BY provider ASC, model ASC, valid_from DESC
            LIMIT 500
            """
            ),
            {
                "provider": provider_filter,
                "model": model_filter,
                "model_like": f"%{model_filter}%" if model_filter else None,
                "include_expired": include_expired,
                "now": datetime.now(UTC),
            },
        )

    return result.mappings().all()


@router.post("", status_code=201, response_model=PricingRecord)
async def create_pricing(body: PricingCreate, user=Depends(get_current_user)):
    require_admin(user)

    provider = normalize_name(body.provider)
    model = body.model.strip()
    if not model:
        raise HTTPException(422, "Model is required")

    valid_from = body.valid_from or datetime.now(UTC)

    async with get_db() as db:
        async with db.begin():
            await db.execute(
                text(
                    """
                UPDATE model_pricing
                SET valid_to = :valid_from
                WHERE provider = :provider
                  AND model = :model
                  AND valid_from < :valid_from
                  AND (valid_to IS NULL OR valid_to > :valid_from)
                """
                ),
                {"provider": provider, "model": model, "valid_from": valid_from},
            )
            result = await db.execute(
                text(
                    """
                INSERT INTO model_pricing (
                    provider, model, input_cost_per_1k_tokens,
                    output_cost_per_1k_tokens, valid_from
                )
                VALUES (:provider, :model, :input_cost, :output_cost, :valid_from)
                RETURNING id, provider, model, input_cost_per_1k_tokens,
                    output_cost_per_1k_tokens, valid_from, valid_to
                """
                ),
                {
                    "provider": provider,
                    "model": model,
                    "input_cost": body.input_cost_per_1k_tokens,
                    "output_cost": body.output_cost_per_1k_tokens,
                    "valid_from": valid_from,
                },
            )
            row = result.mappings().one()

    await invalidate_pricing_cache(provider, model)
    return row


@router.patch("/{pricing_id}", response_model=PricingRecord)
async def update_pricing(
    pricing_id: int, body: PricingUpdate, user=Depends(get_current_user)
):
    require_admin(user)

    updates = {
        key: value for key, value in body.model_dump().items() if value is not None
    }
    if not updates:
        raise HTTPException(400, "No fields to update")

    set_clause = ", ".join(f"{key} = :{key}" for key in updates)
    async with get_db() as db:
        result = await db.execute(
            text(
                f"""
            UPDATE model_pricing SET {set_clause}
            WHERE id = :pricing_id
            RETURNING id, provider, model, input_cost_per_1k_tokens,
                output_cost_per_1k_tokens, valid_from, valid_to
            """  # nosec B608
            ),
            {**updates, "pricing_id": pricing_id},
        )
        row = result.mappings().one_or_none()
        if not row:
            raise HTTPException(404, "Pricing record not found")

        await db.commit()

    await invalidate_pricing_cache(row["provider"], row["model"])
    return row


@router.post("/{pricing_id}/end", response_model=PricingRecord)
async def end_pricing(
    pricing_id: int, body: PricingEndDate, user=Depends(get_current_user)
):
    require_admin(user)

    valid_to = body.valid_to or datetime.now(UTC)

    async with get_db() as db:
        result = await db.execute(
            text(
                """
            UPDATE model_pricing SET valid_to = :valid_to
            WHERE id = :pricing_id
            RETURNING id, provider, model, input_cost_per_1k_tokens,
                output_cost_per_1k_tokens, valid_from, valid_to
            """
            ),
            {"pricing_id": pricing_id, "valid_to": valid_to},
        )
        row = result.mappings().one_or_none()
        if not row:
            raise HTTPException(404, "Pricing record not found")

        await db.commit()

    await invalidate_pricing_cache(row["provider"], row["model"])
    return row
