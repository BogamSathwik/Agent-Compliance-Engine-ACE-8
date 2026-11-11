"""Application and Version management API endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationLatestStatusResponse,
)
from app.schemas.application_version import (
    ApplicationVersionCreate,
    ApplicationVersionResponse,
    ApplicationVersionsListResponse,
)
from app.schemas.certification import CertificationResponse
from app.services.application_service import ApplicationService
from app.services.certification_service import CertificationService

router = APIRouter(prefix="/api/v1/applications", tags=["Applications"])


@router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new application",
)
def create_application(
    app_in: ApplicationCreate,
    db: Session = Depends(get_db),
):
    """Register a new AI agent or web application with ACE."""
    return ApplicationService.create_application(db, app_in)


@router.get(
    "/{application_id}",
    response_model=ApplicationResponse,
    summary="Get application details",
)
def get_application(
    application_id: str,
    db: Session = Depends(get_db),
):
    """Fetch details of a registered application by ID."""
    return ApplicationService.get_application(db, application_id)


@router.get(
    "/{application_id}/status",
    response_model=ApplicationLatestStatusResponse,
    summary="Get application certification status",
)
def get_application_status(
    application_id: str,
    db: Session = Depends(get_db),
):
    """Fetch the latest certification run and status for an application."""
    app = ApplicationService.get_application(db, application_id)
    latest_run = ApplicationService.get_latest_certification_status(db, application_id)

    latest_cert_data = None
    if latest_run:
        _, summary = CertificationService.get_certification(db, latest_run.certification_id)
        latest_cert_data = {
            "certification_id": latest_run.certification_id,
            "application_version": latest_run.application_version,
            "commit_hash": latest_run.commit_hash,
            "status": latest_run.status,
            "started_at": latest_run.started_at,
            "completed_at": latest_run.completed_at,
            "created_at": latest_run.created_at,
            "findings_summary": summary.model_dump() if summary else None,
        }

    return ApplicationLatestStatusResponse(
        application_id=app.application_id,
        name=app.name,
        application_type=app.application_type,
        current_version=app.current_version,
        latest_certification=latest_cert_data,
    )


@router.get(
    "/{application_id}/publication-status",
    summary="Get application publication eligibility status",
)
def get_application_publication_status(
    application_id: str,
    version: Optional[str] = Query(None, description="Exact application version (defaults to current_version)"),
    db: Session = Depends(get_db),
):
    """Evaluate whether the application version is verified and eligible for AgentGen Pro publication."""
    app = ApplicationService.get_application(db, application_id)
    target_version = version or app.current_version
    from app.models.certification import CertificationRun, CertificationStatusEnum

    latest_run = (
        db.query(CertificationRun)
        .filter(
            CertificationRun.application_id == app.application_id,
            CertificationRun.application_version == target_version,
        )
        .order_by(CertificationRun.created_at.desc(), CertificationRun.id.desc())
        .first()
    )

    if latest_run and latest_run.status == CertificationStatusEnum.READY_TO_PUBLISH.value:
        status_val = CertificationStatusEnum.READY_TO_PUBLISH.value
        is_ready = True
    elif latest_run and latest_run.status == CertificationStatusEnum.ERROR.value:
        status_val = CertificationStatusEnum.ERROR.value
        is_ready = False
    else:
        status_val = CertificationStatusEnum.NOT_READY.value
        is_ready = False

    from app.services.publication_service import PublicationService
    pub_service = PublicationService()
    stat = pub_service.get_publication_status(db, app.application_id, target_version)

    return {
        "application_id": app.application_id,
        "application_name": app.name,
        "version": target_version,
        "latest_certification_id": latest_run.certification_id if latest_run else None,
        "publication_status": status_val,
        "is_ready_to_publish": is_ready,
        "is_eligible_for_publication": stat["is_eligible_for_publication"],
        "publication_record_status": stat["publication_status"],
        "is_published": stat["is_published"],
        "latest_publication_id": stat["latest_publication_id"],
        "external_publication_id": stat["external_publication_id"],
        "evaluated_at": latest_run.completed_at.isoformat() if latest_run and latest_run.completed_at else None,
    }


@router.get(
    "",
    response_model=List[ApplicationResponse],
    summary="List applications",
)
def list_applications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Retrieve paginated list of registered applications."""
    apps, _ = ApplicationService.list_applications(db, skip=skip, limit=limit)
    return apps


@router.post(
    "/{application_id}/versions",
    response_model=ApplicationVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new application version",
)
def create_application_version(
    application_id: str,
    version_in: ApplicationVersionCreate,
    db: Session = Depends(get_db),
):
    """Register a new semantic version for an application."""
    return ApplicationService.create_application_version(db, application_id, version_in)


@router.get(
    "/{application_id}/versions",
    response_model=ApplicationVersionsListResponse,
    summary="List all versions for an application",
)
def list_application_versions(
    application_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve all versions registered for an application."""
    versions = ApplicationService.list_application_versions(db, application_id)
    version_responses = [ApplicationVersionResponse.model_validate(v) for v in versions]
    return ApplicationVersionsListResponse(
        application_id=application_id,
        total_versions=len(version_responses),
        versions=version_responses,
    )


@router.post(
    "/{application_id}/re-certify",
    summary="Request explicit re-certification for an application",
    status_code=status.HTTP_202_ACCEPTED,
)
def request_application_recertification(
    application_id: str,
    version: Optional[str] = Query(None, description="Target version (defaults to current_version)"),
    submission_id: Optional[str] = Query(None, description="Optional submission identifier"),
    commit_hash: Optional[str] = Query(None, description="Optional commit hash"),
    db: Session = Depends(get_db),
):
    """Trigger a distinct re-certification run for an application."""
    cert_service = CertificationService()
    new_run = cert_service.request_recertification(
        db=db,
        application_id=application_id,
        version=version,
        submission_id=submission_id,
        commit_hash=commit_hash,
        actor="api_client",
    )
    return {
        "certification_id": new_run.certification_id,
        "application_id": new_run.application_id,
        "application_version": new_run.application_version,
        "commit_hash": new_run.commit_hash,
        "submission_id": new_run.submission_id,
        "trigger_type": new_run.trigger_type,
        "status": new_run.status,
        "created_at": new_run.created_at.isoformat() if new_run.created_at else None,
        "message": "Re-certification run queued successfully",
    }


@router.get(
    "/{application_id}/certification-runs",
    response_model=List[CertificationResponse],
    summary="List certification runs for an application",
)
def list_application_certification_runs(
    application_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Retrieve certification run history for a specific application."""
    ApplicationService.get_application(db, application_id)
    from app.models.certification import CertificationRun
    runs = (
        db.query(CertificationRun)
        .filter(CertificationRun.application_id == application_id)
        .order_by(CertificationRun.created_at.desc(), CertificationRun.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    results = []
    for run in runs:
        _, summary = CertificationService.get_certification(db, run.certification_id)
        results.append(
            CertificationResponse(
                id=run.id,
                certification_id=run.certification_id,
                application_id=run.application_id,
                application_version=run.application_version,
                application_version_id=run.application_version_id,
                commit_hash=run.commit_hash,
                submission_id=run.submission_id,
                trigger_type=run.trigger_type,
                policy_version=run.policy_version,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                created_at=run.created_at,
                updated_at=run.updated_at,
                findings_summary=summary,
            )
        )
    return results
