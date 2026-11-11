"""Pydantic v2 schemas for AgentGen Pro Publication Integration."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.publication import PublicationStatusEnum


class PublicationRequest(BaseModel):
    application_id: Optional[str] = Field(None, description="Target application identifier")
    version: Optional[str] = Field(None, description="Specific semantic version to publish. Defaults to current version if omitted.")
    notes: Optional[str] = Field(None, description="Optional release notes or submission metadata.")


class PublicationResponse(BaseModel):
    publication_id: str
    application_id: str
    application_version: str
    certification_id: str
    submission_id: Optional[str] = None
    status: PublicationStatusEnum
    external_publication_id: Optional[str] = None
    external_status: Optional[str] = None
    external_confirmation: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    requested_by: str = "operator"
    retry_count: int = 0
    created_at: datetime
    confirmed_at: Optional[datetime] = None
    is_published: bool = False

    model_config = ConfigDict(from_attributes=True)


class PublicationStatusResponse(BaseModel):
    application_id: str
    application_name: str
    version: str
    is_eligible_for_publication: bool
    certification_status: str
    latest_certification_id: Optional[str] = None
    publication_status: str
    is_published: bool
    latest_publication_id: Optional[str] = None
    external_publication_id: Optional[str] = None
    last_evaluated_at: Optional[str] = None
    last_published_at: Optional[str] = None


class PublicationFailureDetails(BaseModel):
    publication_id: str
    application_id: str
    version: str
    certification_id: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    last_attempt_at: datetime
    retry_permitted: bool = True
    retry_count: int = 0


class ExternalPublicationConfirmationRequest(BaseModel):
    external_publication_id: str
    status: str = Field(..., description="External status, e.g. PUBLISHED or FAILED")
    confirmation_details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
