from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PricingRecord(BaseModel):
    id: int
    provider: str
    model: str
    input_cost_per_1k_tokens: Decimal
    output_cost_per_1k_tokens: Decimal
    valid_from: datetime
    valid_to: datetime | None = None


class PricingCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    input_cost_per_1k_tokens: Decimal = Field(ge=0, decimal_places=10)
    output_cost_per_1k_tokens: Decimal = Field(ge=0, decimal_places=10)
    valid_from: datetime | None = None


class PricingUpdate(BaseModel):
    input_cost_per_1k_tokens: Decimal | None = Field(default=None, ge=0)
    output_cost_per_1k_tokens: Decimal | None = Field(default=None, ge=0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class PricingEndDate(BaseModel):
    valid_to: datetime | None = None
