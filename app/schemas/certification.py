"""Pydantic v2 schemas for Certification Runs."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.certification import CertificationStatusEnum, TriggerTypeEnum


class FindingsSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    not_verified: int = 0
    partial: int = 0


class CertificationCreate(BaseModel):
    application_id: str = Field(..., min_length=1, max_length=64, description="Target application identifier")
    version: Optional[str] = Field(None, max_length=64, description="Target version to certify. Defaults to application current version if omitted.")
    commit_hash: Optional[str] = Field(None, max_length=128, description="Target commit hash")
    submission_id: Optional[str] = Field(None, max_length=64, description="Upstream submission or build ID from AgentGen")
    trigger_type: Optional[TriggerTypeEnum] = Field(default=TriggerTypeEnum.MANUAL, description="Trigger event origin")
    policy_version: Optional[str] = Field(default="v1.0", max_length=64, description="Policy rule set version")


class CertificationCreateResponse(BaseModel):
    certification_id: str
    application_id: str
    application_version: str
    commit_hash: Optional[str] = None
    submission_id: Optional[str] = None
    trigger_type: Optional[str] = None
    status: CertificationStatusEnum
    created_at: datetime
    message: str = "Certification run queued successfully"

    model_config = ConfigDict(from_attributes=True)


class CertificationResponse(BaseModel):
    id: int
    certification_id: str
    application_id: str
    application_version: str
    application_version_id: Optional[int] = None
    commit_hash: Optional[str] = None
    submission_id: Optional[str] = None
    trigger_type: Optional[str] = None
    policy_version: Optional[str] = None
    status: CertificationStatusEnum
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    findings_summary: Optional[FindingsSummary] = None

    model_config = ConfigDict(from_attributes=True)
