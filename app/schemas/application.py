"""Pydantic v2 schemas for Applications."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.application import ApplicationTypeEnum


class ApplicationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Application display name")
    description: Optional[str] = Field(None, description="Optional application description")
    application_type: ApplicationTypeEnum = Field(
        default=ApplicationTypeEnum.AI_AGENT,
        description="Type of application: AI_AGENT, WEB_APP, OTHER",
    )
    repository_url: Optional[str] = Field(None, max_length=512, description="Source code repository URL")


class ApplicationCreate(ApplicationBase):
    application_id: str = Field(..., min_length=1, max_length=64, description="Unique application identifier")
    version: Optional[str] = Field(None, max_length=64, description="Initial application version")
    current_version: Optional[str] = Field(None, max_length=64, description="Initial application version (alias)")
    commit_hash: Optional[str] = Field(None, max_length=128, description="Source repository commit hash")
    submission_id: Optional[str] = Field(None, max_length=64, description="Upstream submission or build ID")

    def get_version(self) -> str:
        """Resolve initial version from either version or current_version."""
        return self.version or self.current_version or "1.0.0"


class ApplicationResponse(ApplicationBase):
    id: int
    application_id: str
    current_version: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationLatestStatusResponse(BaseModel):
    application_id: str
    name: str
    application_type: str
    current_version: str
    latest_certification: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)
