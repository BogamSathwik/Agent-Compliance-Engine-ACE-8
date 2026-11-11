"""Certification API endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.certification import (
    CertificationCreate,
    CertificationCreateResponse,
    CertificationResponse,
)
from app.schemas.finding import FindingsListResponse, FindingResponse
from app.schemas.certification_check import ChecksListResponse, CheckResponse
from app.schemas.evidence import EvidenceListResponse, EvidenceResponse
from app.schemas.audit_event import AuditTrailResponse, AuditEventResponse
from app.schemas.remediation import RemediationReport, RemediationStatusUpdateRequest
from app.services.certification_service import CertificationService
from app.services.evidence_service import EvidenceService
from app.services.remediation_service import RemediationService

router = APIRouter(prefix="/api/v1/certifications", tags=["Certifications"])
cert_service = CertificationService()


@router.post(
    "",
    response_model=CertificationCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an autonomous certification run",
)
def start_certification(
    cert_in: CertificationCreate,
    db: Session = Depends(get_db),
):
    """Start an autonomous certification run for an application.

    1. Validates the application exists.
    2. Enforces idempotency against duplicate active submission runs.
    3. Generates a unique certification_id.
    4. Creates a certification run with status QUEUED.
    5. Queues a background certification job.
    6. Returns the certification_id.
    """
    run = cert_service.create_certification_run(db, cert_in)
    return CertificationCreateResponse(
        certification_id=run.certification_id,
        application_id=run.application_id,
        application_version=run.application_version,
        commit_hash=run.commit_hash,
        submission_id=run.submission_id,
        trigger_type=run.trigger_type,
        status=run.status,
        created_at=run.created_at,
        message="Certification run queued successfully",
    )


@router.get(
    "",
    response_model=List[CertificationResponse],
    summary="List certification runs",
)
def list_certifications(
    application_id: Optional[str] = Query(None, description="Filter by application ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Retrieve paginated list of certification runs."""
    from app.models.certification import CertificationRun
    query = db.query(CertificationRun)
    if application_id:
        query = query.filter(CertificationRun.application_id == application_id)
    if status:
        query = query.filter(CertificationRun.status == status)
    runs = query.order_by(CertificationRun.created_at.desc(), CertificationRun.id.desc()).offset(skip).limit(limit).all()

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


@router.get(
    "/{certification_id}",
    response_model=CertificationResponse,
    summary="Get certification run details",
)
def get_certification(
    certification_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve certification run details, timestamps, status, and findings summary."""
    run, summary = CertificationService.get_certification(db, certification_id)
    return CertificationResponse(
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


@router.get(
    "/{certification_id}/findings",
    response_model=FindingsListResponse,
    summary="Get certification findings and remediation guidance",
)
def get_certification_findings(
    certification_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve all findings, verification statuses, and exact remediation instructions."""
    findings = CertificationService.get_findings(db, certification_id)
    finding_responses = [FindingResponse.model_validate(f) for f in findings]
    return FindingsListResponse(
        certification_id=certification_id,
        total_findings=len(finding_responses),
        findings=finding_responses,
    )


@router.get(
    "/{certification_id}/checks",
    response_model=ChecksListResponse,
    summary="Get certification check verifications",
)
def get_certification_checks(
    certification_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve all checks executed during the certification run."""
    checks = CertificationService.get_checks(db, certification_id)
    check_responses = [CheckResponse.model_validate(c) for c in checks]
    return ChecksListResponse(
        certification_id=certification_id,
        total_checks=len(check_responses),
        checks=check_responses,
    )


@router.get(
    "/{certification_id}/evidence",
    response_model=EvidenceListResponse,
    summary="Get collected evidence for certification",
)
def get_certification_evidence(
    certification_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve all verifiable evidence records collected during certification."""
    CertificationService.get_certification(db, certification_id)
    evidence_records = EvidenceService.get_evidence_for_certification(db, certification_id)
    evidence_responses = [EvidenceResponse.model_validate(e) for e in evidence_records]
    return EvidenceListResponse(
        certification_id=certification_id,
        total_evidence=len(evidence_responses),
        evidence=evidence_responses,
    )


@router.get(
    "/{certification_id}/audit",
    response_model=AuditTrailResponse,
    summary="Get audit trail for certification",
)
def get_certification_audit_trail(
    certification_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve complete immutable audit history for this certification."""
    CertificationService.get_certification(db, certification_id)
    audit_events = EvidenceService.get_audit_trail(db, certification_id)
    event_responses = [AuditEventResponse.model_validate(a) for a in audit_events]
    return AuditTrailResponse(
        certification_id=certification_id,
        total_events=len(event_responses),
        events=event_responses,
    )


@router.get(
    "/{certification_id}/remediation",
    response_model=RemediationReport,
    summary="Get structured remediation report",
)
def get_certification_remediation(
    certification_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve structured remediation report detailing exact corrective actions."""
    run, _ = CertificationService.get_certification(db, certification_id)
    findings = CertificationService.get_findings(db, certification_id)
    return RemediationService.generate_remediation_report(
        certification_id=run.certification_id,
        application_id=run.application_id,
        application_version=run.application_version,
        overall_status=run.status,
        findings=findings,
    )


@router.patch(
    "/{certification_id}/remediation",
    response_model=FindingResponse,
    summary="Update remediation lifecycle status for a finding",
)
def update_remediation_status(
    certification_id: str,
    update_in: RemediationStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update remediation status (OPEN -> IN_PROGRESS -> RESOLVED) for an identified finding."""
    finding = RemediationService.update_remediation_status(
        db=db,
        certification_id=certification_id,
        status=update_in.status,
        finding_id=update_in.finding_id,
        finding_code=update_in.finding_code,
        notes=update_in.notes,
        actor="api_client",
    )
    return FindingResponse.model_validate(finding)


@router.post(
    "/{certification_id}/re-certify",
    response_model=CertificationCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request explicit re-certification for a prior run",
)
def request_recertification(
    certification_id: str,
    db: Session = Depends(get_db),
):
    """Trigger a distinct re-certification run based on a prior certification attempt."""
    prior_run, _ = CertificationService.get_certification(db, certification_id)
    new_run = cert_service.request_recertification(
        db=db,
        application_id=prior_run.application_id,
        certification_id=prior_run.certification_id,
        version=prior_run.application_version,
        submission_id=prior_run.submission_id,
        commit_hash=prior_run.commit_hash,
        actor="api_client",
    )
    return CertificationCreateResponse(
        certification_id=new_run.certification_id,
        application_id=new_run.application_id,
        application_version=new_run.application_version,
        commit_hash=new_run.commit_hash,
        submission_id=new_run.submission_id,
        trigger_type=new_run.trigger_type,
        status=new_run.status,
        created_at=new_run.created_at,
        message="Re-certification run queued successfully",
    )
