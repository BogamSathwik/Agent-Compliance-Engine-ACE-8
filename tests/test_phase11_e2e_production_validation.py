"""Phase 11: ACE End-to-End Integration and Production Readiness Validation Tests.

Validates the complete 10-step certification flow, deterministic publication gate,
remediation lifecycle, historical audit preservation, and bidirectional MCP contracts.
"""

import pytest
from app.models.application import Application, ApplicationTypeEnum
from app.models.certification import CertificationRun, CertificationStatusEnum, TriggerTypeEnum
from app.models.certification_check import CertificationCheck, CheckStatusEnum
from app.models.evidence import Evidence
from app.models.finding import CertificationFinding, FindingCategoryEnum, FindingStatusEnum, RemediationStatusEnum
from app.schemas.certification import CertificationCreate
from app.services.certification_service import CertificationService
from app.services.publication_service import PublicationService
from app.mcp.server import ACEMCPServer
from app.integrations.contracts import (
    DocumentCategoryVerification,
    DocumentVerificationResult,
    QAVerificationResult,
    RuleEvaluationResult,
    SingleRuleEvaluation,
    MANDATORY_17_DOC_CATEGORIES,
    MANDATORY_9_AGENT_RULES,
)


def _build_doc_result(app_id: str, ver: str, fail_cat: str = None) -> DocumentVerificationResult:
    cat_verifications = []
    missing = []
    verified_count = 0

    for cat in MANDATORY_17_DOC_CATEGORIES:
        is_pass = (cat != fail_cat)
        if is_pass:
            verified_count += 1
            st = FindingStatusEnum.PASS
            reason = None
        else:
            missing.append(cat)
            st = FindingStatusEnum.FAIL
            reason = f"Missing required document for {cat}"

        cat_verifications.append(
            DocumentCategoryVerification(
                category=cat,
                requirement_id=f"DOC-{cat.replace('_', '-')}",
                status=st,
                title=f"Doc: {cat}",
                description=f"Verification for {cat}",
                remediation=reason,
                source_version=ver,
                source_run_id=f"RAG-RUN-{ver}",
                raw_evidence={"category": cat, "verified": is_pass},
            )
        )

    all_ok = (fail_cat is None)
    return DocumentVerificationResult(
        status=FindingStatusEnum.PASS if all_ok else FindingStatusEnum.FAIL,
        category=FindingCategoryEnum.DOCUMENT,
        required_count=17,
        verified_count=verified_count,
        missing_categories=missing,
        title="17 Document Requirements Verification",
        description="All 17 categories verified" if all_ok else f"Failed {fail_cat}",
        external_run_id=f"RAG-P11-{ver}",
        external_application_id=app_id,
        external_version=ver,
        category_verifications=cat_verifications,
        raw_evidence={"all_verified": all_ok, "missing": missing},
    )


def _build_qa_result(app_id: str, ver: str, passed: bool = True) -> QAVerificationResult:
    return QAVerificationResult(
        status=FindingStatusEnum.PASS if passed else FindingStatusEnum.FAIL,
        category=FindingCategoryEnum.QA,
        passed=passed,
        pass_count=50 if passed else 40,
        fail_count=0 if passed else 10,
        critical_failures=0 if passed else 2,
        external_run_id=f"QA-P11-{ver}",
        external_application_id=app_id,
        external_version=ver,
        title="Authoritative QA Suite Verification",
        description="All tests passed" if passed else "Tests failed",
        raw_evidence={"passed": passed},
    )


def _build_rule_result(app_id: str, ver: str, passed: bool = True) -> RuleEvaluationResult:
    evals = [
        SingleRuleEvaluation(
            rule_id=r["rule_id"],
            rule_name=r["name"],
            category=r["category"],
            passed=passed,
            status=FindingStatusEnum.PASS if passed else FindingStatusEnum.FAIL,
            reason=f"Rule {r['name']} status",
        )
        for r in MANDATORY_9_AGENT_RULES
    ]
    return RuleEvaluationResult(
        status=FindingStatusEnum.PASS if passed else FindingStatusEnum.FAIL,
        category=FindingCategoryEnum.RULE,
        total_rules=9,
        passed_rules=9 if passed else 0,
        failed_rules=0 if passed else 9,
        passed=passed,
        external_run_id=f"RULE-P11-{ver}",
        external_application_id=app_id,
        external_version=ver,
        title="9-Rule Governance Evaluation",
        description="Governance rules compliant",
        raw_evidence={"passed": passed},
        rule_evaluations=evals,
    )


class MockDocVerifier:
    def __init__(self, fail_category=None):
        self.fail_category = fail_category

    def verify_application_documents(self, application_id: str, version: str, **kwargs):
        return _build_doc_result(application_id, version, self.fail_category)


class MockQAVerifier:
    def __init__(self, passed=True):
        self.passed = passed

    def verify_application_qa(self, application_id: str, version: str, **kwargs):
        return _build_qa_result(application_id, version, self.passed)


class MockRuleVerifier:
    def __init__(self, passed=True):
        self.passed = passed

    def evaluate_agent_rules(self, application_id: str, version: str, **kwargs):
        return _build_rule_result(application_id, version, self.passed)


def test_complete_e2e_certification_and_recertification_flow(client, db_session):
    """Execute complete 10-step certification flow and verify PolicyEngine authority."""
    app_id = "APP-E2E-TEST-001"
    app_version = "1.0.0"
    commit = "c0ffee123456"
    sub_id = "SUB-E2E-001"

    # Step 1: Register an application
    app_res = client.post(
        "/api/v1/applications",
        json={
            "application_id": app_id,
            "name": "E2E Test Agent",
            "application_type": "AI_AGENT",
            "version": app_version,
            "commit_hash": commit,
        },
    )
    assert app_res.status_code == 201
    assert app_res.json()["application_id"] == app_id

    # Step 2: Start an initial certification run with a failed category
    failing_service = CertificationService(
        document_verifier=MockDocVerifier(fail_category="API_DOCUMENTATION"),
        qa_verifier=MockQAVerifier(passed=True),
        rule_verifier=MockRuleVerifier(passed=True),
    )
    cert_in1 = CertificationCreate(
        application_id=app_id,
        version=app_version,
        commit_hash=commit,
        submission_id=sub_id,
        trigger_type=TriggerTypeEnum.MANUAL,
    )
    queued_run1 = failing_service.create_certification_run(db_session, cert_in1)
    run1 = failing_service.execute_certification_pipeline(
        db=db_session,
        certification_id=queued_run1.certification_id,
    )

    # Step 3, 4, 5: Verify all 17 document categories, 9 agent rules, and QA are recorded
    checks = db_session.query(CertificationCheck).filter(CertificationCheck.certification_id == run1.certification_id).all()
    check_ids = {c.check_id for c in checks}
    assert "CHK-DOC-001" in check_ids
    assert "CHK-QA-001" in check_ids
    assert "CHK-RULE-001" in check_ids
    assert "CHK-VER-001" in check_ids

    findings = db_session.query(CertificationFinding).filter(CertificationFinding.certification_id == run1.certification_id).all()
    finding_codes = {f.finding_code for f in findings}
    for cat in MANDATORY_17_DOC_CATEGORIES:
        assert f"FINDING-DOC-{cat}" in finding_codes
    assert "FINDING-RULE-001" in finding_codes
    assert "FINDING-QA-001" in finding_codes

    # Step 6: Validate evidence provenance and hashes
    evidence_records = db_session.query(Evidence).filter(Evidence.certification_id == run1.certification_id).all()
    assert len(evidence_records) >= 3
    for ev in evidence_records:
        assert ev.evidence_data is not None
        assert ev.source_system is not None

    # Step 7: Confirm findings saved against correct run
    findings = db_session.query(CertificationFinding).filter(CertificationFinding.certification_id == run1.certification_id).all()
    assert len(findings) >= 1
    failed_finding = next((f for f in findings if "API_DOCUMENTATION" in (f.finding_code or f.title)), None)
    assert failed_finding is not None
    assert failed_finding.remediation_status == RemediationStatusEnum.OPEN.value

    # Step 8: Confirm final deterministic decision is NOT_READY
    assert run1.status == CertificationStatusEnum.NOT_READY.value

    # Ensure publication is blocked by backend PolicyEngine
    pub_attempt = client.post(f"/api/v1/applications/{app_id}/publish", json={"version": app_version})
    assert pub_attempt.status_code == 400
    assert pub_attempt.json()["error"]["code"] == "PUBLICATION_INELIGIBLE"

    # Step 9: Update remediation status and trigger re-certification
    rem_update = client.patch(
        f"/api/v1/certifications/{run1.certification_id}/remediation",
        json={
            "finding_id": failed_finding.id,
            "status": "RESOLVED",
            "notes": "Added API_DOCUMENTATION in commit c0ffee789",
        },
    )
    assert rem_update.status_code == 200
    assert rem_update.json()["remediation_status"] == "RESOLVED"

    # Re-certify with corrected verifiers (all passing)
    passing_service = CertificationService(
        document_verifier=MockDocVerifier(fail_category=None),
        qa_verifier=MockQAVerifier(passed=True),
        rule_verifier=MockRuleVerifier(passed=True),
    )
    recert_queued = passing_service.request_recertification(
        db=db_session,
        application_id=app_id,
        certification_id=run1.certification_id,
        version=app_version,
        commit_hash="c0ffee789",
        submission_id="SUB-E2E-002",
    )
    recert_run = passing_service.execute_certification_pipeline(
        db=db_session,
        certification_id=recert_queued.certification_id,
    )

    # Step 10: Verify new run achieves READY_TO_PUBLISH and preserves previous run
    assert recert_run.status == CertificationStatusEnum.READY_TO_PUBLISH.value
    assert recert_run.certification_id != run1.certification_id

    # Verify history is preserved
    all_runs = db_session.query(CertificationRun).filter(CertificationRun.application_id == app_id).all()
    assert len(all_runs) == 2
    statuses = {r.status for r in all_runs}
    assert CertificationStatusEnum.NOT_READY.value in statuses
    assert CertificationStatusEnum.READY_TO_PUBLISH.value in statuses

    # Now verify publication status allows publication
    pub_stat_res = client.get(f"/api/v1/applications/{app_id}/publication-status")
    assert pub_stat_res.status_code == 200
    assert pub_stat_res.json()["is_ready_to_publish"] is True
    assert pub_stat_res.json()["is_eligible_for_publication"] is True


def test_mcp_capabilities_and_policy_enforcement(client, db_session):
    """Verify bidirectional MCP exposes ACE tools and respects PolicyEngine boundaries."""
    server = ACEMCPServer()

    # Discover tools
    tools = server.list_tools()
    tool_names = [t["name"] for t in tools]
    assert "start_certification" in tool_names
    assert "get_certification_status" in tool_names
    assert "get_publication_status" in tool_names
    assert "request_publication" in tool_names

    # Check unverified application returns NOT_READY
    app_record = Application(
        application_id="APP-MCP-TEST-002",
        name="MCP Agent",
        current_version="1.0.0",
        application_type=ApplicationTypeEnum.AI_AGENT.value,
    )
    db_session.add(app_record)
    db_session.commit()

    status_res = server.call_tool(
        db=db_session,
        tool_name="get_publication_status",
        arguments={"application_id": "APP-MCP-TEST-002", "version": "1.0.0"},
    )
    assert status_res["publication_status"] == "NOT_READY"
    assert status_res["is_ready_to_publish"] is False


def test_frontend_production_assets_served(client):
    """Verify frontend assets are built and correctly served from root and assets."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "ACE" in res.text
