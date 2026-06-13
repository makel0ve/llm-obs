from pydantic import BaseModel, Field


class ProjectSettingsUpdate(BaseModel):
    retention_days: int = Field(ge=7, le=365)
