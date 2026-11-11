"""Pydantic v2 schemas for Evidence."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.evidence import SourceSystemEnum


class EvidenceBase(BaseModel):
    source_system: SourceSystemEnum = Field(..., description="System originating the evidence")
    source_reference: Optional[str] = Field(None, max_length=255, description="External reference ID or URI")
    evidence_type: str = Field(..., min_length=1, max_length=64, description="Type/schema of the evidence payload")
    evidence_data: Dict[str, Any] = Field(..., description="Structured JSON evidence payload")
    check_id: Optional[str] = Field(None, max_length=64, description="Originating check ID")
    source_version: Optional[str] = Field(None, max_length=64, description="Version reported by source system")
    source_run_id: Optional[str] = Field(None, max_length=128, description="Execution run ID from source system")
    source_timestamp: Optional[datetime] = Field(None, description="Timestamp recorded by source system")
    hash: Optional[str] = Field(None, max_length=128, description="Cryptographic fingerprint of evidence payload")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence metric if applicable")


class EvidenceCreate(EvidenceBase):
    certification_id: str
    finding_id: Optional[int] = None


class EvidenceResponse(EvidenceBase):
    id: int
    certification_id: str
    finding_id: Optional[int] = None
    collected_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceListResponse(BaseModel):
    certification_id: str
    total_evidence: int
    evidence: List[EvidenceResponse]

    model_config = ConfigDict(from_attributes=True)
