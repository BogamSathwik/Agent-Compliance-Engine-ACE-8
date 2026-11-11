"""REST API endpoints for AgentGen Pro Publication Integration."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import PublicationNotFoundError
from app.schemas.publication import (
    PublicationFailureDetails,
    PublicationRequest,
    PublicationResponse,
    PublicationStatusResponse,
)
from app.services.publication_service import PublicationService

router = APIRouter(prefix="/api/v1", tags=["Publications"])


@router.post(
    "/applications/{application_id}/publish",
    response_model=PublicationResponse,
    status_code=status.HTTP_200_OK,
    summary="Request publication of an eligible application version to AgentGen Pro",
)
def request_publication(
    application_id: str,
    payload: Optional[PublicationRequest] = None,
    db: Session = Depends(get_db),
):
    """Revalidate policy eligibility and submit publication request to AgentGen Pro."""
    service = PublicationService()
    version = payload.version if payload else None
    notes = payload.notes if payload else None
    record = service.request_publication(
        db=db,
        application_id=application_id,
        version=version,
        notes=notes,
        actor="api_client",
    )
    is_pub = record.status == "PUBLISHED"
    return PublicationResponse(
        publication_id=record.publication_id,
        application_id=record.application_id,
        application_version=record.application_version,
        certification_id=record.certification_id,
        submission_id=record.submission_id,
        status=record.status,
        external_publication_id=record.external_publication_id,
        external_status=record.external_status,
        external_confirmation=record.external_confirmation,
        error_code=record.error_code,
        error_message=record.error_message,
        requested_by=record.requested_by,
        retry_count=record.retry_count,
        created_at=record.created_at,
        confirmed_at=record.confirmed_at,
        is_published=is_pub,
    )


@router.get(
    "/applications/{application_id}/publication-failures",
    response_model=PublicationFailureDetails,
    status_code=status.HTTP_200_OK,
    summary="Retrieve failure details for the latest failed publication attempt",
)
def get_publication_failures(
    application_id: str,
    version: Optional[str] = Query(None, description="Target version"),
    publication_id: Optional[str] = Query(None, description="Optional publication ID"),
    db: Session = Depends(get_db),
):
    """Retrieve actionable publication failure details without leaking credentials."""
    service = PublicationService()
    rec = service.get_failure_details(db, application_id, version, publication_id)
    if not rec:
        raise PublicationNotFoundError(f"No failure records found for {application_id}")

    return PublicationFailureDetails(
        publication_id=rec.publication_id,
        application_id=rec.application_id,
        version=rec.application_version,
        certification_id=rec.certification_id,
        error_code=rec.error_code,
        error_message=rec.error_message,
        last_attempt_at=rec.updated_at or rec.created_at,
        retry_permitted=True,
        retry_count=rec.retry_count,
    )


@router.post(
    "/applications/{application_id}/verify-publication",
    response_model=PublicationResponse,
    status_code=status.HTTP_200_OK,
    summary="Reconcile and verify external publication status with AgentGen Pro",
)
def verify_external_publication(
    application_id: str,
    version: Optional[str] = Query(None, description="Target version"),
    publication_id: Optional[str] = Query(None, description="Optional publication ID"),
    db: Session = Depends(get_db),
):
    """Query AgentGen Pro to authoritatively verify in-flight or unknown publication status."""
    service = PublicationService()
    record = service.verify_external_publication(
        db=db,
        application_id=application_id,
        version=version,
        publication_id=publication_id,
        actor="api_client",
    )
    is_pub = record.status == "PUBLISHED"
    return PublicationResponse(
        publication_id=record.publication_id,
        application_id=record.application_id,
        application_version=record.application_version,
        certification_id=record.certification_id,
        submission_id=record.submission_id,
        status=record.status,
        external_publication_id=record.external_publication_id,
        external_status=record.external_status,
        external_confirmation=record.external_confirmation,
        error_code=record.error_code,
        error_message=record.error_message,
        requested_by=record.requested_by,
        retry_count=record.retry_count,
        created_at=record.created_at,
        confirmed_at=record.confirmed_at,
        is_published=is_pub,
    )
