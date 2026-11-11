"""Pydantic schemas for Requirements."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class RequirementResponse(BaseModel):
    id: int
    requirement_id: str = Field(..., description="Unique requirement code (e.g. DOC-ARCH-01, RULE-01)")
    category: str
    name: str
    description: str
    mandatory: bool
    active: bool
    policy_version: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
