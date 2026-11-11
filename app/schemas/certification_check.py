"""Pydantic schemas for Certification Checks."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.certification_check import CheckTypeEnum, CheckStatusEnum


class CheckBase(BaseModel):
    check_id: str = Field(..., description="Check identifier (e.g. CHK-DOC-001)")
    check_type: CheckTypeEnum = Field(..., description="Check type category")
    check_name: str = Field(..., description="Human-readable check title")
    status: CheckStatusEnum = Field(default=CheckStatusEnum.PENDING, description="Verification status")
    source_system: str = Field(..., description="Originating subsystem (e.g. MYBLOCKS_RAG)")


class CheckResponse(CheckBase):
    id: int
    certification_id: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChecksListResponse(BaseModel):
    certification_id: str
    total_checks: int
    checks: List[CheckResponse]

    model_config = ConfigDict(from_attributes=True)
