import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import text

from app.core.db import get_db
from app.core.redis import get_redis


class CostService:
    CACHE_TTL = 3600

    def _cache_key(self, provider: str, model: str, at_time: datetime) -> str:
        return f"pricing:{provider}:{model}:{at_time.isoformat()}"

    async def calculate(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        at_time: datetime | None = None,
    ) -> Decimal:
        at_time = at_time or datetime.now(UTC)
        pricing = await self._get_pricing(provider, model, at_time)
        if not pricing:
            return Decimal("0")

        input_cost = Decimal(str(pricing["input"])) * input_tokens / Decimal("1000")
        output_cost = Decimal(str(pricing["output"])) * output_tokens / Decimal("1000")

        return (input_cost + output_cost).quantize(Decimal("0.00000001"))

    async def _get_pricing(
        self, provider: str, model: str, at_time: datetime
    ) -> dict | None:
        cache_key = self._cache_key(provider, model, at_time)
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        async with get_db() as db:
            result = await db.execute(
                text(
                    """
                SELECT input_cost_per_1k_tokens as inp,
                    output_cost_per_1k_tokens as out
                FROM model_pricing
                WHERE provider = :p AND model = :m
                    AND valid_from <= :t
                    AND (valid_to IS NULL OR valid_to > :t)
                ORDER BY valid_from DESC LIMIT 1
                """
                ),
                {"p": provider, "m": model, "t": at_time},
            )
            row = result.mappings().one_or_none()

        if not row:
            return None

        pricing = {"input": str(row["inp"]), "output": str(row["out"])}
        await redis.setex(cache_key, self.CACHE_TTL, json.dumps(pricing))

        return pricing
