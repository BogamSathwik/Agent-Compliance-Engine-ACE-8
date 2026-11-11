"""Pydantic schemas for Application Versions."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ApplicationVersionBase(BaseModel):
    version: str = Field(..., min_length=1, max_length=64, description="Semantic version string (e.g. 1.4.2)")
    commit_hash: Optional[str] = Field(None, max_length=128, description="Source repository commit hash")
    source_reference: Optional[str] = Field(None, max_length=255, description="Source code or artifact repository reference")
    submission_id: Optional[str] = Field(None, max_length=64, description="Upstream submission or build ID")


class ApplicationVersionCreate(ApplicationVersionBase):
    pass


class ApplicationVersionResponse(ApplicationVersionBase):
    id: int
    application_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationVersionsListResponse(BaseModel):
    application_id: str
    total_versions: int
    versions: List[ApplicationVersionResponse]

    model_config = ConfigDict(from_attributes=True)
