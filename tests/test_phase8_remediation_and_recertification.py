"""Phase 8 Remediation Lifecycle and Automatic Re-certification Tests.

Validates:
1. Remediation creation from failed checks with full actionable details
2. Resolving an issue only after successful re-verification (status update != compliance)
3. Re-certification creating a distinct run and preserving prior history
4. Stale evidence not being reused
5. Application/version mismatch handling
6. Retry idempotency (prevent duplicate active queued runs)
7. Publication remaining NOT_READY until every mandatory condition passes
"""

import pytest
from datetime import datetime, timezone
from app.models.certification import CertificationStatusEnum, TriggerTypeEnum, CertificationRun
from app.models.finding import CertificationFinding, FindingStatusEnum, RemediationStatusEnum, FindingCategoryEnum
from app.models.evidence import Evidence, SourceSystemEnum
from app.integrations.contracts import (
    DocumentVerificationResult,
    DocumentCategoryVerification,
    QAVerificationResult,
    RuleEvaluationResult,
    SingleRuleEvaluation,
    MANDATORY_17_DOC_CATEGORIES,
    MANDATORY_9_AGENT_RULES,
)
from app.services.certification_service import CertificationService
from app.services.application_service import ApplicationService
from app.services.remediation_service import RemediationService
from app.services.evidence_service import EvidenceService
from app.schemas.application import ApplicationCreate
from app.schemas.certification import CertificationCreate
from app.schemas.remediation import RemediationStatusUpdateRequest
from app.mcp.server import ACEMCPServer


def _build_passing_doc_result(app_id: str, version: str) -> DocumentVerificationResult:
    return DocumentVerificationResult(
        status=FindingStatusEnum.PASS,
        required_count=17,
        verified_count=17,
        missing_categories=[],
        title="17 Documents Verified",
        description="All 17/17 verified",
        category_verifications=[
            DocumentCategoryVerification(
                category=cat,
                requirement_id=f"DOC-{cat.replace('_', '-')}",
                status=FindingStatusEnum.PASS,
                title=f"Doc {cat}",
                description="Verified in RAG",
                source_version=version,
                source_reference=f"rag-doc://{app_id}/{version}/{cat}",
                raw_evidence={"category": cat, "version": version, "verified": True},
            )
            for cat in MANDATORY_17_DOC_CATEGORIES
        ],
    )


def _build_failing_doc_result(app_id: str, version: str) -> DocumentVerificationResult:
    # 16 pass, 1 (OTHER) fails
    cats = []
    for cat in MANDATORY_17_DOC_CATEGORIES:
        is_fail = (cat == "OTHER")
        cats.append(
            DocumentCategoryVerification(
                category=cat,
                requirement_id=f"DOC-{cat.replace('_', '-')}",
                status=FindingStatusEnum.FAIL if is_fail else FindingStatusEnum.PASS,
                title=f"Doc {cat}",
                description="Failed in RAG: document not found" if is_fail else "Verified in RAG",
                remediation=f"Ingest {cat} into MyBlocks RAG" if is_fail else None,
                source_version=version,
                source_reference=f"rag-doc://{app_id}/{version}/{cat}",
                raw_evidence={"category": cat, "version": version, "verified": not is_fail},
            )
        )
    return DocumentVerificationResult(
        status=FindingStatusEnum.FAIL,
        required_count=17,
        verified_count=16,
        missing_categories=["OTHER"],
        title="Documentation Incomplete",
        description="Category OTHER failed",
        category_verifications=cats,
    )


def _build_passing_qa_result(app_id: str, version: str) -> QAVerificationResult:
    return QAVerificationResult(
        status=FindingStatusEnum.PASS,
        passed=True,
        pass_count=50,
        fail_count=0,
        critical_failures=0,
        title="QA Test Suite Passed",
        description="All 50 tests passed",
        external_application_id=app_id,
        external_version=version,
        external_run_id=f"QA-RUN-{app_id}",
        raw_evidence={"application_id": app_id, "version": version, "passed": True, "status": "PASS"},
    )


def _build_failing_qa_result(app_id: str, version: str) -> QAVerificationResult:
    return QAVerificationResult(
        status=FindingStatusEnum.FAIL,
        passed=False,
        pass_count=40,
        fail_count=10,
        critical_failures=2,
        title="QA Test Suite Failed",
        description="10 tests failed in MyBlocks QA",
        remediation="Fix regression tests in test suite and re-run",
        external_application_id=app_id,
        external_version=version,
        external_run_id=f"QA-RUN-FAIL-{app_id}",
        raw_evidence={"application_id": app_id, "version": version, "passed": False, "status": "FAIL"},
    )


def _build_passing_rule_result(app_id: str, version: str) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        status=FindingStatusEnum.PASS,
        total_rules=9,
        passed_rules=9,
        failed_rules=0,
        passed=True,
        title="9-Rule Agent Evaluation Passed",
        description="All 9 rules pass",
        external_application_id=app_id,
        external_version=version,
        external_run_id=f"RULE-SCAN-{app_id}",
        rule_evaluations=[
            SingleRuleEvaluation(
                rule_id=r["rule_id"],
                rule_name=r["name"],
                category=r["category"],
                passed=True,
                status=FindingStatusEnum.PASS,
            )
            for r in MANDATORY_9_AGENT_RULES
        ],
        raw_evidence={"application_id": app_id, "version": version, "passed": True, "total_rules": 9, "passed_rules": 9},
    )


class MockDocVerifier:
    def __init__(self, func):
        self.func = func

    def verify_application_documents(self, application_id, version, **kwargs):
        return self.func(application_id, version)


class MockQAVerifier:
    def __init__(self, func):
        self.func = func

    def verify_application_qa(self, application_id, version, **kwargs):
        return self.func(application_id, version)


class MockRuleVerifier:
    def __init__(self, func):
        self.func = func

    def evaluate_agent_rules(self, application_id, version, **kwargs):
        return self.func(application_id, version)


def test_phase8_remediation_creation_from_failed_checks(client, db_session):
    """1. Failed checks generate structured, actionable remediation items with OPEN status."""
    app_id = "APP-P8-REM-01"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Remediation Agent", version=version),
    )

    doc_verifier = MockDocVerifier(lambda a, v: _build_failing_doc_result(a, v))
    qa_verifier = MockQAVerifier(lambda a, v: _build_failing_qa_result(a, v))
    rule_verifier = MockRuleVerifier(lambda a, v: _build_passing_rule_result(a, v))

    service = CertificationService(
        document_verifier=doc_verifier,
        qa_verifier=qa_verifier,
        rule_verifier=rule_verifier,
    )
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id=app_id, version=version, submission_id="SUB-P8-01"),
    )
    completed_run = service.execute_certification_pipeline(db_session, run.certification_id)
    assert completed_run.status == CertificationStatusEnum.NOT_READY.value

    # Query via REST endpoint
    res = client.get(f"/api/v1/certifications/{run.certification_id}/remediation")
    assert res.status_code == 200
    report = res.json()
    assert report["overall_status"] == "NOT_READY"
    assert report["actionable_items_count"] > 0

    # Verify actionable fields on each item
    for item in report["items"]:
        assert item["finding_id"] is not None
        assert item["requirement"] != ""
        assert item["status"] in ["FAIL", "NOT_VERIFIED", "PARTIAL"]
        assert item["remediation_status"] == "OPEN"
        assert item["reason"] != ""
        assert item["required_action"] != ""
        assert item["target_system"] in ["MYBLOCKS_RAG", "MYBLOCKS_QA", "RULE_ENGINE", "ACE_VERSION_SERVICE", "ACE"]

    # Query via MCP tool
    mcp_res = ACEMCPServer._tool_get_remediation({"certification_id": run.certification_id}, db_session)
    assert mcp_res["actionable_items_count"] == report["actionable_items_count"]
    assert mcp_res["items"][0]["remediation_status"] == "OPEN"


def test_phase8_resolving_issue_only_after_successful_reverification(client, db_session):
    """2. Updating remediation status to RESOLVED does NOT grant READY_TO_PUBLISH without re-verification."""
    app_id = "APP-P8-LIFECYCLE"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Lifecycle Agent", version=version),
    )

    doc_verifier = MockDocVerifier(lambda a, v: _build_failing_doc_result(a, v))
    qa_verifier = MockQAVerifier(lambda a, v: _build_passing_qa_result(a, v))
    rule_verifier = MockRuleVerifier(lambda a, v: _build_passing_rule_result(a, v))

    service = CertificationService(
        document_verifier=doc_verifier,
        qa_verifier=qa_verifier,
        rule_verifier=rule_verifier,
    )
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id=app_id, version=version, submission_id="SUB-P8-LIFE-01"),
    )
    completed_run = service.execute_certification_pipeline(db_session, run.certification_id)
    assert completed_run.status == CertificationStatusEnum.NOT_READY.value

    # Find the failing finding
    findings = service.get_findings(db_session, run.certification_id)
    failing_finding = next(f for f in findings if f.status != FindingStatusEnum.PASS.value)
    assert failing_finding.remediation_status == "OPEN"

    # Step 1: Transition OPEN -> IN_PROGRESS via REST
    patch_res = client.patch(
        f"/api/v1/certifications/{run.certification_id}/remediation",
        json={
            "finding_id": failing_finding.id,
            "status": "IN_PROGRESS",
            "notes": "Engineer updating documentation",
        },
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["remediation_status"] == "IN_PROGRESS"

    # Step 2: Transition IN_PROGRESS -> RESOLVED via MCP tool
    mcp_update = ACEMCPServer._tool_update_remediation_status(
        {
            "certification_id": run.certification_id,
            "finding_id": failing_finding.id,
            "status": "RESOLVED",
            "notes": "Document uploaded to RAG",
        },
        db_session,
    )
    assert mcp_update["remediation_status"] == "RESOLVED"

    # CRITICAL: Publication status MUST REMAIN NOT_READY! Marking resolved is not verification!
    pub_res = ACEMCPServer._tool_get_publication_status({"application_id": app_id, "version": version}, db_session)
    assert pub_res["publication_status"] == "NOT_READY"
    assert pub_res["is_ready_to_publish"] is False


def test_phase8_recertification_creating_distinct_run(client, db_session):
    """3. Re-certification creates a distinct run, preserves previous run & audit history."""
    app_id = "APP-P8-RECERT"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Recert Agent", version=version),
    )

    doc_verifier = MockDocVerifier(lambda a, v: _build_failing_doc_result(a, v))
    qa_verifier = MockQAVerifier(lambda a, v: _build_passing_qa_result(a, v))
    rule_verifier = MockRuleVerifier(lambda a, v: _build_passing_rule_result(a, v))

    service = CertificationService(
        document_verifier=doc_verifier,
        qa_verifier=qa_verifier,
        rule_verifier=rule_verifier,
    )

    # Initial failing run
    run1 = service.create_certification_run(
        db_session,
        CertificationCreate(application_id=app_id, version=version, submission_id="SUB-P8-RECERT-01"),
    )
    run1 = service.execute_certification_pipeline(db_session, run1.certification_id)
    assert run1.status == CertificationStatusEnum.NOT_READY.value

    # Request re-certification via REST
    recert_res = client.post(f"/api/v1/certifications/{run1.certification_id}/re-certify")
    assert recert_res.status_code == 202
    run2_data = recert_res.json()
    assert run2_data["certification_id"] != run1.certification_id
    assert run2_data["trigger_type"] == TriggerTypeEnum.RE_CERTIFICATION.value

    # Prior run 1 is completely preserved
    run1_db = db_session.query(CertificationRun).filter(CertificationRun.certification_id == run1.certification_id).first()
    assert run1_db is not None
    assert run1_db.status == CertificationStatusEnum.NOT_READY.value
    findings_1 = service.get_findings(db_session, run1.certification_id)
    assert len(findings_1) > 0

    # Audit event recorded for re-certification request
    audit = EvidenceService.get_audit_trail(db_session, run2_data["certification_id"])
    assert any(a.event_type == "RE_CERTIFICATION_REQUESTED" for a in audit)


def test_phase8_stale_evidence_not_being_reused(db_session):
    """4. Stale evidence from a prior run is never treated as current or passing."""
    app_id = "APP-P8-STALE"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Stale Ev Agent", version=version),
    )

    # Mock verifier providing stale flag in evidence
    def _stale_qa(a, v):
        res = _build_passing_qa_result(a, v)
        res.raw_evidence["is_stale"] = True
        return res

    service = CertificationService(
        document_verifier=MockDocVerifier(lambda a, v: _build_passing_doc_result(a, v)),
        qa_verifier=MockQAVerifier(_stale_qa),
        rule_verifier=MockRuleVerifier(lambda a, v: _build_passing_rule_result(a, v)),
    )

    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id=app_id, version=version, submission_id="SUB-P8-STALE-01"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)
    # Stale evidence causes PolicyEngine to reject publication
    assert completed.status == CertificationStatusEnum.NOT_READY.value


def test_phase8_application_version_mismatch(db_session):
    """5. Re-certification with version mismatch evaluates strictly to NOT_READY."""
    app_id = "APP-P8-VER-MISMATCH"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Version Mismatch Agent", version=version),
    )

    # QA verifier reports results for an older version 0.9.0
    def _mismatched_qa(a, v):
        res = _build_passing_qa_result(a, "0.9.0")
        res.external_version = "0.9.0"
        return res

    service = CertificationService(
        document_verifier=MockDocVerifier(lambda a, v: _build_passing_doc_result(a, v)),
        qa_verifier=MockQAVerifier(_mismatched_qa),
        rule_verifier=MockRuleVerifier(lambda a, v: _build_passing_rule_result(a, v)),
    )

    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id=app_id, version=version, submission_id="SUB-P8-VER-01"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)
    assert completed.status == CertificationStatusEnum.NOT_READY.value


def test_phase8_retry_idempotency(db_session):
    """6. Idempotent retry prevents duplicate active queued runs for the same request."""
    app_id = "APP-P8-IDEMP"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Idempotency Agent", version=version),
    )

    service = CertificationService()

    # Request 1 creates queued run
    run1 = service.request_recertification(
        db_session,
        application_id=app_id,
        version=version,
        submission_id="SUB-P8-IDEMP-SAME",
    )
    assert run1.status == CertificationStatusEnum.QUEUED.value

    # Duplicate request with same submission_id while first is QUEUED returns exact same run
    run1_duplicate = service.request_recertification(
        db_session,
        application_id=app_id,
        version=version,
        submission_id="SUB-P8-IDEMP-SAME",
    )
    assert run1.certification_id == run1_duplicate.certification_id


def test_phase8_publication_remaining_not_ready_until_every_condition_passes(db_session):
    """7. Publication remains NOT_READY until all 17 docs, 9 rules, QA, version, and evidence pass."""
    app_id = "APP-P8-ALL-COND"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="All Conditions Agent", version=version),
    )

    # Stage 1: Document fails -> NOT_READY
    service_fail_doc = CertificationService(
        document_verifier=MockDocVerifier(lambda a, v: _build_failing_doc_result(a, v)),
        qa_verifier=MockQAVerifier(lambda a, v: _build_passing_qa_result(a, v)),
        rule_verifier=MockRuleVerifier(lambda a, v: _build_passing_rule_result(a, v)),
    )
    r1 = service_fail_doc.create_certification_run(
        db_session,
        CertificationCreate(application_id=app_id, version=version, submission_id="SUB-P8-S1"),
    )
    res1 = service_fail_doc.execute_certification_pipeline(db_session, r1.certification_id)
    assert res1.status == CertificationStatusEnum.NOT_READY.value

    # Stage 2: Re-certify with document fixed, but QA failing -> still NOT_READY
    service_fail_qa = CertificationService(
        document_verifier=MockDocVerifier(lambda a, v: _build_passing_doc_result(a, v)),
        qa_verifier=MockQAVerifier(lambda a, v: _build_failing_qa_result(a, v)),
        rule_verifier=MockRuleVerifier(lambda a, v: _build_passing_rule_result(a, v)),
    )
    r2 = service_fail_qa.request_recertification(
        db_session,
        application_id=app_id,
        version=version,
        submission_id="SUB-P8-S2",
    )
    res2 = service_fail_qa.execute_certification_pipeline(db_session, r2.certification_id)
    assert res2.status == CertificationStatusEnum.NOT_READY.value

    # Stage 3: Re-certify with all verifiers passing -> READY_TO_PUBLISH
    service_all_pass = CertificationService(
        document_verifier=MockDocVerifier(lambda a, v: _build_passing_doc_result(a, v)),
        qa_verifier=MockQAVerifier(lambda a, v: _build_passing_qa_result(a, v)),
        rule_verifier=MockRuleVerifier(lambda a, v: _build_passing_rule_result(a, v)),
    )
    r3 = service_all_pass.request_recertification(
        db_session,
        application_id=app_id,
        version=version,
        submission_id="SUB-P8-S3",
    )
    res3 = service_all_pass.execute_certification_pipeline(db_session, r3.certification_id)
    assert res3.status == CertificationStatusEnum.READY_TO_PUBLISH.value

    # Publication status reports READY_TO_PUBLISH
    pub_res = ACEMCPServer._tool_get_publication_status({"application_id": app_id, "version": version}, db_session)
    assert pub_res["publication_status"] == "READY_TO_PUBLISH"
    assert pub_res["is_ready_to_publish"] is True
