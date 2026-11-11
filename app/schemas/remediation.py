"""Pydantic schemas for Actionable Remediation."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RemediationItem(BaseModel):
    finding_id: Optional[int] = Field(None, description="Internal finding identifier")
    requirement: str = Field(..., description="Requirement identifier not satisfied")
    finding_code: Optional[str] = Field(None, description="Finding correlation code")
    check_id: Optional[str] = Field(None, description="Originating check ID")
    status: str = Field(..., description="Status (e.g. NOT_VERIFIED, FAIL)")
    remediation_status: str = Field(default="OPEN", description="Remediation lifecycle: OPEN, IN_PROGRESS, RESOLVED")
    severity: str = Field(..., description="Severity level")
    reason: str = Field(..., description="Detailed explanation of why the requirement is not satisfied")
    missing_or_failed_evidence: str = Field(..., description="Evidence that is absent or failed validation")
    required_action: str = Field(..., description="Exact corrective action required")
    target_system: str = Field(..., description="Subsystem that must be checked or re-run (e.g. MYBLOCKS_RAG, MYBLOCKS_QA)")


class RemediationStatusUpdateRequest(BaseModel):
    finding_id: Optional[int] = Field(None, description="Internal finding ID to update")
    finding_code: Optional[str] = Field(None, description="Finding correlation code to update")
    status: str = Field(..., description="Target remediation lifecycle status: OPEN, IN_PROGRESS, RESOLVED")
    notes: Optional[str] = Field(None, description="Optional operator or system notes")


class RemediationReport(BaseModel):
    certification_id: str
    application_id: str
    application_version: str
    overall_status: str
    actionable_items_count: int
    items: List[RemediationItem]

    model_config = ConfigDict(from_attributes=True)
