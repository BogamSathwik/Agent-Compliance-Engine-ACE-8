"""Tests for Worker, Pipeline execution, and Policy Evaluation."""

from app.workers.celery_app import celery_app
from app.workers.certification_worker import run_certification_task
from app.services.application_service import ApplicationService
from app.services.certification_service import CertificationService
from app.schemas.application import ApplicationCreate
from app.schemas.certification import CertificationCreate
from app.models.certification import CertificationStatusEnum
from app.models.finding import (
    CertificationFinding,
    FindingCategoryEnum,
    FindingStatusEnum,
    FindingSeverityEnum,
)
from app.models.evidence import Evidence
from app.models.audit_event import AuditEvent


def test_worker_initialization():
    """Verify Celery app configuration and task registration."""
    assert celery_app.main == "ace_workers"
    registered_tasks = celery_app.tasks.keys()
    assert "run_certification_task" in registered_tasks


def test_certification_pipeline_execution(db_session):
    """Verify full end-to-end certification pipeline execution.

    - Loads run
    - Transitions through QUEUED -> RUNNING -> NOT_READY
    - Never uses BLOCKED or REJECTED
    - Persists DOCUMENT, QA, and RULE findings with clear remediation
    - Records structured evidence and audit events
    """
    # 1. Setup Application
    app_in = ApplicationCreate(
        application_id="APP-PIPELINE-1",
        name="Pipeline Verification Agent",
        version="1.0.0",
        commit_hash="c0ffee1",
    )
    ApplicationService.create_application(db_session, app_in)

    # 2. Queue certification
    cert_service = CertificationService()
    run = cert_service.create_certification_run(
        db_session,
        CertificationCreate(
            application_id="APP-PIPELINE-1",
            version="1.0.0",
            commit_hash="c0ffee1",
        ),
    )
    assert run.status == CertificationStatusEnum.QUEUED.value

    # 3. Execute certification pipeline (as worker does)
    completed_run = cert_service.execute_certification_pipeline(
        db_session, run.certification_id
    )

    # 4. Verify status transition: Phase 1 evaluates to NOT_READY (not faked pass, never BLOCKED)
    assert completed_run.status == CertificationStatusEnum.NOT_READY.value
    assert completed_run.status not in ["BLOCKED", "REJECTED"]
    assert completed_run.started_at is not None
    assert completed_run.completed_at is not None

    # 5. Verify findings generated (17 DOCUMENT categories, QA, RULE, VERSION)
    findings = (
        db_session.query(CertificationFinding)
        .filter(CertificationFinding.certification_id == run.certification_id)
        .all()
    )
    assert len(findings) == 20

    categories = {f.category for f in findings}
    assert FindingCategoryEnum.DOCUMENT.value in categories
    assert FindingCategoryEnum.QA.value in categories
    assert FindingCategoryEnum.RULE.value in categories
    assert FindingCategoryEnum.VERSION.value in categories

    for f in findings:
        if f.status != FindingStatusEnum.PASS.value:
            assert f.status == FindingStatusEnum.NOT_VERIFIED.value
            assert f.remediation is not None
            assert len(f.remediation) > 0

    # 6. Verify evidence collection (17 DOCUMENT category records + QA + RULE + VERSION)
    evidence_records = (
        db_session.query(Evidence)
        .filter(Evidence.certification_id == run.certification_id)
        .all()
    )
    assert len(evidence_records) == 20
    source_systems = {e.source_system for e in evidence_records}
    assert "MYBLOCKS_RAG" in source_systems
    assert "MYBLOCKS_QA" in source_systems
    assert "RULE_ENGINE" in source_systems
    assert "ACE" in source_systems


    # 7. Verify audit events recorded
    audit_events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.certification_id == run.certification_id)
        .all()
    )
    event_types = {a.event_type.upper() for a in audit_events}
    assert "CERTIFICATION_CREATED" in event_types or "CERTIFICATION_QUEUED" in event_types
    assert "CERTIFICATION_STARTED" in event_types
    assert "CERTIFICATION_COMPLETED" in event_types



def test_deterministic_policy_evaluation():
    """Verify deterministic publication decision rules."""
    # Case 1: Empty findings -> NOT_READY
    assert CertificationService.evaluate_policy([]) == CertificationStatusEnum.NOT_READY

    # Case 2: One non-passing finding -> NOT_READY
    mixed_findings = [
        CertificationFinding(
            certification_id="CERT-TEST-1",
            category="DOCUMENT",
            status=FindingStatusEnum.PASS.value,
            severity=FindingSeverityEnum.MEDIUM.value,
            title="Docs verified",
            description="All verified",
        ),
        CertificationFinding(
            certification_id="CERT-TEST-1",
            category="QA",
            status=FindingStatusEnum.NOT_VERIFIED.value,
            severity=FindingSeverityEnum.HIGH.value,
            title="QA pending",
            description="QA suite pending",
        ),
    ]
    assert CertificationService.evaluate_policy(mixed_findings) == CertificationStatusEnum.NOT_READY

    # Case 3: All passing findings -> READY_TO_PUBLISH
    all_pass_findings = [
        CertificationFinding(
            certification_id="CERT-TEST-2",
            category="DOCUMENT",
            status=FindingStatusEnum.PASS.value,
            severity=FindingSeverityEnum.INFO.value,
            title="Docs pass",
            description="17/17 verified",
        ),
        CertificationFinding(
            certification_id="CERT-TEST-2",
            category="QA",
            status=FindingStatusEnum.PASS.value,
            severity=FindingSeverityEnum.INFO.value,
            title="QA pass",
            description="100% tests passed",
        ),
        CertificationFinding(
            certification_id="CERT-TEST-2",
            category="RULE",
            status=FindingStatusEnum.PASS.value,
            severity=FindingSeverityEnum.INFO.value,
            title="9 Rules pass",
            description="9/9 rules satisfied",
        ),
    ]
    assert CertificationService.evaluate_policy(all_pass_findings) == CertificationStatusEnum.READY_TO_PUBLISH
