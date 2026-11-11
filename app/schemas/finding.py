"""Pydantic v2 schemas for Certification Findings."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.finding import (
    FindingCategoryEnum,
    FindingStatusEnum,
    FindingSeverityEnum,
)


class FindingBase(BaseModel):
    category: FindingCategoryEnum = Field(..., description="Finding category")
    requirement_id: Optional[str] = Field(None, max_length=64, description="Requirement identifier")
    check_id: Optional[str] = Field(None, max_length=64, description="Originating check ID")
    finding_code: Optional[str] = Field(None, max_length=64, description="Deterministic finding code (e.g. DOC-REQ-001)")
    status: FindingStatusEnum = Field(..., description="Verification status: PASS, FAIL, NOT_VERIFIED, PARTIAL")
    remediation_status: Optional[str] = Field(default="OPEN", description="Remediation lifecycle: OPEN, IN_PROGRESS, RESOLVED")
    severity: FindingSeverityEnum = Field(default=FindingSeverityEnum.MEDIUM, description="Finding severity")
    title: str = Field(..., min_length=1, max_length=255, description="Brief finding title")
    description: str = Field(..., min_length=1, description="Detailed explanation of finding")
    remediation: Optional[str] = Field(None, description="Exact remediation guidance")


class FindingCreate(FindingBase):
    certification_id: str


class FindingResponse(FindingBase):
    id: int
    certification_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FindingsListResponse(BaseModel):
    certification_id: str
    total_findings: int
    findings: List[FindingResponse]

    model_config = ConfigDict(from_attributes=True)
