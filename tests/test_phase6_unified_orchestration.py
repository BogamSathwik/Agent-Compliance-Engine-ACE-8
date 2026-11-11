"""Phase 6 Focused Verification: MCP Orchestration + Unified Evidence Engine.

Tests:
1. All integrations passing -> READY_TO_PUBLISH
2. One integration failing -> FAIL, NOT_READY, other integrations still collected
3. One integration unavailable (timeout/error) -> NOT_VERIFIED, NOT_READY, independent results collected
4. Version mismatch -> NOT_VERIFIED, NOT_READY
5. Incomplete evidence -> NOT_READY
6. Retry and idempotency behavior -> safe idempotency, no duplicate evidence, audit preserved
"""

import httpx
from datetime import datetime, timezone
from app.models.certification import CertificationRun, CertificationStatusEnum, TriggerTypeEnum
from app.models.certification_check import CertificationCheck, CheckStatusEnum, CheckTypeEnum
from app.models.finding import CertificationFinding, FindingStatusEnum, FindingCategoryEnum
from app.models.evidence import Evidence, SourceSystemEnum
from app.models.integration_run import IntegrationRun
from app.core.context import CertificationContext
from app.services.application_service import ApplicationService
from app.services.certification_service import CertificationService
from app.services.policy_engine import PolicyEngine
from app.services.evidence_service import EvidenceService
from app.schemas.application import ApplicationCreate
from app.schemas.certification import CertificationCreate
from app.integrations.contracts import (
    DocumentCategoryVerification,
    DocumentVerificationResult,
    QAVerificationResult,
    RuleEvaluationResult,
    SingleRuleEvaluation,
    MANDATORY_17_DOC_CATEGORIES,
    MANDATORY_9_AGENT_RULES,
)
from app.mcp.server import ACEMCPServer


def _build_passing_doc_result(app_id: str, ver: str, run_id: str = "RAG-P6-PASS") -> DocumentVerificationResult:
    return DocumentVerificationResult(
        status=FindingStatusEnum.PASS,
        category=FindingCategoryEnum.DOCUMENT,
        required_count=17,
        verified_count=17,
        missing_categories=[],
        title="All 17 Mandatory Documents Verified",
        description="Authoritative documentation verified across all 17 categories.",
        external_run_id=run_id,
        external_application_id=app_id,
        external_version=ver,
        category_verifications=[
            DocumentCategoryVerification(
                category=cat,
                requirement_id=f"DOC-{cat.replace('_', '-')}",
                status=FindingStatusEnum.PASS,
                title=f"Doc: {cat} Verified",
                description=f"Verified authoritative content for {cat}.",
                source_version=ver,
                source_run_id=run_id,
                raw_evidence={"category": cat, "verified": True, "app_id": app_id, "ver": ver},
            )
            for cat in MANDATORY_17_DOC_CATEGORIES
        ],
    )


def _build_passing_qa_result(app_id: str, ver: str, run_id: str = "QA-P6-PASS") -> QAVerificationResult:
    return QAVerificationResult(
        status=FindingStatusEnum.PASS,
        category=FindingCategoryEnum.QA,
        passed=True,
        pass_count=60,
        fail_count=0,
        critical_failures=0,
        external_run_id=run_id,
        external_application_id=app_id,
        external_version=ver,
        title="Authoritative QA Suite Passed",
        description="All 60 automated tests passed successfully.",
        raw_evidence={"passed": True, "pass_count": 60, "fail_count": 0, "run_id": run_id},
    )


def _build_passing_rule_result(app_id: str, ver: str, run_id: str = "RULE-P6-PASS") -> RuleEvaluationResult:
    evals = [
        SingleRuleEvaluation(
            rule_id=r["rule_id"],
            rule_name=r["name"],
            category=r["category"],
            passed=True,
            status=FindingStatusEnum.PASS,
            reason=f"Rule {r['name']} fully compliant",
        )
        for r in MANDATORY_9_AGENT_RULES
    ]
    return RuleEvaluationResult(
        status=FindingStatusEnum.PASS,
        category=FindingCategoryEnum.RULE,
        total_rules=9,
        passed_rules=9,
        failed_rules=0,
        passed=True,
        external_run_id=run_id,
        external_application_id=app_id,
        external_version=ver,
        title="All 9 Agent Rules Compliant",
        description="All mandatory governance rules satisfied.",
        raw_evidence={"total_rules": 9, "passed_rules": 9, "run_id": run_id},
        rule_evaluations=evals,
    )


class MockDocVerifier:
    def __init__(self, result_fn):
        self.result_fn = result_fn

    def verify_application_documents(self, application_id: str, version: str, **kwargs):
        return self.result_fn(application_id, version, **kwargs)


class MockQAVerifier:
    def __init__(self, result_fn):
        self.result_fn = result_fn

    def verify_application_qa(self, application_id: str, version: str, **kwargs):
        return self.result_fn(application_id, version, **kwargs)


class MockRuleVerifier:
    def __init__(self, result_fn):
        self.result_fn = result_fn

    def evaluate_agent_rules(self, application_id: str, version: str, **kwargs):
        return self.result_fn(application_id, version, **kwargs)


def test_phase6_all_integrations_passing(db_session):
    """1. All integrations passing -> READY_TO_PUBLISH with full unified evidence and provenance."""
    app_id = "APP-P6-ALL-PASS"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="All Pass Agent", version=version),
    )

    doc_verifier = MockDocVerifier(lambda a, v, **kw: _build_passing_doc_result(a, v))
    qa_verifier = MockQAVerifier(lambda a, v, **kw: _build_passing_qa_result(a, v))
    rule_verifier = MockRuleVerifier(lambda a, v, **kw: _build_passing_rule_result(a, v))

    service = CertificationService(
        document_verifier=doc_verifier,
        qa_verifier=qa_verifier,
        rule_verifier=rule_verifier,
    )
    run = service.create_certification_run(
        db_session,
        CertificationCreate(
            application_id=app_id,
            version=version,
            commit_hash="commit-p6-pass",
            submission_id="SUB-P6-PASS-01",
        ),
    )

    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    # Outcome must be READY_TO_PUBLISH
    assert completed.status == CertificationStatusEnum.READY_TO_PUBLISH.value

    # All checks must be PASS
    checks = service.get_checks(db_session, run.certification_id)
    assert len(checks) == 4
    for chk in checks:
        assert chk.status == CheckStatusEnum.PASS.value

    # All findings must be PASS
    findings = service.get_findings(db_session, run.certification_id)
    assert len(findings) == 20
    for f in findings:
        assert f.status == FindingStatusEnum.PASS.value

    # Evidence provenance
    evidence_records = EvidenceService.get_evidence_for_certification(db_session, run.certification_id)
    assert len(evidence_records) == 20
    sources = {e.source_system for e in evidence_records}
    assert {"MYBLOCKS_RAG", "MYBLOCKS_QA", "RULE_ENGINE", "ACE"}.issubset(sources)
    for ev in evidence_records:
        assert ev.source_version == version

    # Publication status via MCP tool
    pub_res = ACEMCPServer.call_tool(
        "get_publication_status",
        {"application_id": app_id, "version": version},
        db_session,
    )
    assert pub_res["publication_status"] == "READY_TO_PUBLISH"
    assert pub_res["is_ready_to_publish"] is True


def test_phase6_one_integration_failing(db_session):
    """2. One integration failing -> FAIL, NOT_READY, other integrations still collected."""
    app_id = "APP-P6-ONE-FAIL"
    version = "1.2.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="One Fail Agent", version=version),
    )

    doc_verifier = MockDocVerifier(lambda a, v, **kw: _build_passing_doc_result(a, v))
    # QA fails
    def failing_qa(a, v, **kw):
        return QAVerificationResult(
            status=FindingStatusEnum.FAIL,
            category=FindingCategoryEnum.QA,
            passed=False,
            pass_count=42,
            fail_count=3,
            critical_failures=1,
            external_run_id="QA-RUN-FAILED-02",
            external_application_id=a,
            external_version=v,
            title="QA Test Suite Failed",
            description="3 tests failed, 1 critical security vulnerability found.",
            remediation="Fix critical security vulnerability in authentication module.",
            raw_evidence={"failed": True, "critical_failures": 1},
        )
    qa_verifier = MockQAVerifier(failing_qa)
    rule_verifier = MockRuleVerifier(lambda a, v, **kw: _build_passing_rule_result(a, v))

    service = CertificationService(
        document_verifier=doc_verifier,
        qa_verifier=qa_verifier,
        rule_verifier=rule_verifier,
    )
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id=app_id, version=version),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    # Final publication status must be NOT_READY (never BLOCKED or REJECTED)
    assert completed.status == CertificationStatusEnum.NOT_READY.value
    assert completed.status not in ["BLOCKED", "REJECTED"]

    # Verify that independent results were still collected
    checks = service.get_checks(db_session, run.certification_id)
    doc_chk = next(c for c in checks if c.check_id == "CHK-DOC-001")
    qa_chk = next(c for c in checks if c.check_id == "CHK-QA-001")
    rule_chk = next(c for c in checks if c.check_id == "CHK-RULE-001")

    assert doc_chk.status == "PASS"
    assert qa_chk.status == "FAIL"
    assert rule_chk.status == "PASS"

    # Actionable remediation is generated
    remediation_res = ACEMCPServer.call_tool(
        "get_remediation",
        {"certification_id": run.certification_id},
        db_session,
    )
    assert remediation_res["actionable_items_count"] > 0
    qa_items = [i for i in remediation_res["items"] if i["check_id"] == "CHK-QA-001"]
    assert len(qa_items) == 1
    assert "authentication" in qa_items[0]["required_action"].lower() or "security" in qa_items[0]["reason"].lower()


def test_phase6_one_integration_unavailable(db_session):
    """3. One integration unavailable (raises exception) -> NOT_VERIFIED, NOT_READY, other results collected."""
    app_id = "APP-P6-UNAVAIL"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Unavail Agent", version=version),
    )

    # RAG verifier raises ConnectionError/Timeout
    def unavail_rag(a, v, **kw):
        raise httpx.ConnectTimeout(f"Connection to MyBlocks RAG at https://myblocks.in timed out after 10s")

    doc_verifier = MockDocVerifier(unavail_rag)
    qa_verifier = MockQAVerifier(lambda a, v, **kw: _build_passing_qa_result(a, v))
    rule_verifier = MockRuleVerifier(lambda a, v, **kw: _build_passing_rule_result(a, v))

    service = CertificationService(
        document_verifier=doc_verifier,
        qa_verifier=qa_verifier,
        rule_verifier=rule_verifier,
    )
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id=app_id, version=version),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    # Must complete safely without unhandled exception, final status NOT_READY
    assert completed.status == CertificationStatusEnum.NOT_READY.value

    # Check RAG check was marked NOT_VERIFIED
    checks = service.get_checks(db_session, run.certification_id)
    doc_chk = next(c for c in checks if c.check_id == "CHK-DOC-001")
    assert doc_chk.status == "NOT_VERIFIED"
    assert doc_chk.error_code == "SERVICE_UNAVAILABLE"
    assert "timed out" in doc_chk.error_message.lower()

    # QA and Rule checks were still executed and passed independently
    qa_chk = next(c for c in checks if c.check_id == "CHK-QA-001")
    rule_chk = next(c for c in checks if c.check_id == "CHK-RULE-001")
    assert qa_chk.status == "PASS"
    assert rule_chk.status == "PASS"

    # Integration run for RAG recorded with NOT_VERIFIED and error message
    int_runs = EvidenceService.get_integration_runs(db_session, run.certification_id)
    rag_run = next(i for i in int_runs if i.source_system == "MYBLOCKS_RAG")
    assert rag_run.status == "NOT_VERIFIED"
    assert rag_run.error_code == "SERVICE_UNAVAILABLE"


def test_phase6_version_mismatch(db_session):
    """4. Version mismatch -> NOT_VERIFIED and NOT_READY."""
    app_id = "APP-P6-VER-MISMATCH"
    version = "2.1.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Mismatch Agent", version=version),
    )

    doc_verifier = MockDocVerifier(lambda a, v, **kw: _build_passing_doc_result(a, v))
    # QA reports result for stale version 2.0.0 instead of 2.1.0
    def mismatch_qa(a, v, **kw):
        return QAVerificationResult(
            status=FindingStatusEnum.NOT_VERIFIED,
            category=FindingCategoryEnum.QA,
            passed=False,
            external_run_id="QA-STALE-RUN",
            external_application_id=a,
            external_version="2.0.0",  # Mismatched version
            title="QA Version Discrepancy",
            description=f"Expected version {v}, received 2.0.0",
            remediation=f"Re-run QA for version {v}",
            raw_evidence={"mismatch": True, "reported_version": "2.0.0"},
        )
    qa_verifier = MockQAVerifier(mismatch_qa)
    rule_verifier = MockRuleVerifier(lambda a, v, **kw: _build_passing_rule_result(a, v))

    service = CertificationService(
        document_verifier=doc_verifier,
        qa_verifier=qa_verifier,
        rule_verifier=rule_verifier,
    )
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id=app_id, version=version),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    # QA check must be NOT_VERIFIED
    checks = service.get_checks(db_session, run.certification_id)
    qa_chk = next(c for c in checks if c.check_id == "CHK-QA-001")
    assert qa_chk.status == "NOT_VERIFIED"

    # Version consistency check must be NOT_VERIFIED
    ver_chk = next(c for c in checks if c.check_id == "CHK-VER-001")
    assert ver_chk.status == "NOT_VERIFIED"

    # Final policy decision must be NOT_READY
    assert completed.status == CertificationStatusEnum.NOT_READY.value


def test_phase6_incomplete_evidence():
    """5. Incomplete evidence -> PolicyEngine evaluates to NOT_READY."""
    context = CertificationContext(
        certification_id="CERT-P6-INC-EV",
        application_id="APP-P6-EV",
        application_version="1.0.0",
    )

    passing_checks = [
        CertificationCheck(certification_id="CERT-P6-INC-EV", check_id="CHK-1", check_type="DOCUMENT", check_name="Docs", source_system="MYBLOCKS_RAG", status=CheckStatusEnum.PASS.value),
        CertificationCheck(certification_id="CERT-P6-INC-EV", check_id="CHK-2", check_type="QA", check_name="QA", source_system="MYBLOCKS_QA", status=CheckStatusEnum.PASS.value),
        CertificationCheck(certification_id="CERT-P6-INC-EV", check_id="CHK-3", check_type="RULE", check_name="Rules", source_system="RULE_ENGINE", status=CheckStatusEnum.PASS.value),
    ]
    passing_findings = [
        CertificationFinding(certification_id="CERT-P6-INC-EV", category="DOCUMENT", status=FindingStatusEnum.PASS.value, severity="INFO", title="Docs", description="Pass"),
        CertificationFinding(certification_id="CERT-P6-INC-EV", category="QA", status=FindingStatusEnum.PASS.value, severity="INFO", title="QA", description="Pass"),
        CertificationFinding(certification_id="CERT-P6-INC-EV", category="RULE", status=FindingStatusEnum.PASS.value, severity="INFO", title="Rule", description="Pass"),
    ]

    # Case A: Missing RULE_ENGINE evidence
    incomplete_evidence = [
        Evidence(certification_id="CERT-P6-INC-EV", source_system="MYBLOCKS_RAG", evidence_type="DOC", evidence_data={"ok": True}, source_version="1.0.0"),
        Evidence(certification_id="CERT-P6-INC-EV", source_system="MYBLOCKS_QA", evidence_type="QA", evidence_data={"ok": True}, source_version="1.0.0"),
        # RULE_ENGINE missing!
    ]
    status_a = PolicyEngine.evaluate_certification(context, passing_checks, passing_findings, evidence=incomplete_evidence)
    assert status_a == CertificationStatusEnum.NOT_READY

    # Case B: Evidence has version mismatch (e.g. QA from v0.9.0)
    mismatched_evidence = [
        Evidence(certification_id="CERT-P6-INC-EV", source_system="MYBLOCKS_RAG", evidence_type="DOC", evidence_data={"ok": True}, source_version="1.0.0"),
        Evidence(certification_id="CERT-P6-INC-EV", source_system="MYBLOCKS_QA", evidence_type="QA", evidence_data={"ok": True}, source_version="0.9.0"),
        Evidence(certification_id="CERT-P6-INC-EV", source_system="RULE_ENGINE", evidence_type="RULE", evidence_data={"ok": True}, source_version="1.0.0"),
    ]
    status_b = PolicyEngine.evaluate_certification(context, passing_checks, passing_findings, evidence=mismatched_evidence)
    assert status_b == CertificationStatusEnum.NOT_READY

    # Case C: Evidence data is empty
    empty_ev_data = [
        Evidence(certification_id="CERT-P6-INC-EV", source_system="MYBLOCKS_RAG", evidence_type="DOC", evidence_data={}, source_version="1.0.0"),
        Evidence(certification_id="CERT-P6-INC-EV", source_system="MYBLOCKS_QA", evidence_type="QA", evidence_data={"ok": True}, source_version="1.0.0"),
        Evidence(certification_id="CERT-P6-INC-EV", source_system="RULE_ENGINE", evidence_type="RULE", evidence_data={"ok": True}, source_version="1.0.0"),
    ]
    status_c = PolicyEngine.evaluate_certification(context, passing_checks, passing_findings, evidence=empty_ev_data)
    assert status_c == CertificationStatusEnum.NOT_READY


def test_phase6_retry_and_idempotency_behavior(db_session):
    """6. Retry and idempotency behavior: safe retries, no duplicate evidence, audit preserved."""
    app_id = "APP-P6-IDEMP"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Idemp Agent", version=version),
    )

    service = CertificationService()

    # 1. First submission
    run1 = service.create_certification_run(
        db_session,
        CertificationCreate(
            application_id=app_id,
            version=version,
            submission_id="SUB-P6-IDEMP-01",
        ),
    )

    # 2. Duplicate submission while first is still QUEUED returns the exact same run
    run1_duplicate = service.create_certification_run(
        db_session,
        CertificationCreate(
            application_id=app_id,
            version=version,
            submission_id="SUB-P6-IDEMP-01",
        ),
    )
    assert run1.certification_id == run1_duplicate.certification_id

    # 3. Execute first run to completion
    completed_run1 = service.execute_certification_pipeline(db_session, run1.certification_id)
    assert completed_run1.status == CertificationStatusEnum.NOT_READY.value

    # Count evidence and audit records for run 1
    ev_count_1 = len(EvidenceService.get_evidence_for_certification(db_session, run1.certification_id))
    audit_count_1 = len(EvidenceService.get_audit_trail(db_session, run1.certification_id))
    assert ev_count_1 > 0
    assert audit_count_1 > 0

    # 4. Duplicate submission after completion returns existing run (idempotency guard)
    run1_post = service.create_certification_run(
        db_session,
        CertificationCreate(
            application_id=app_id,
            version=version,
            submission_id="SUB-P6-IDEMP-01",
        ),
    )
    assert run1_post.certification_id == run1.certification_id

    # 5. Explicit RE_CERTIFICATION trigger creates a fresh re-certification run
    retry_run = service.create_certification_run(
        db_session,
        CertificationCreate(
            application_id=app_id,
            version=version,
            submission_id="SUB-P6-IDEMP-01",
            trigger_type=TriggerTypeEnum.RE_CERTIFICATION,
        ),
    )
    assert retry_run.certification_id != run1.certification_id

    # 6. Re-executing evidence collection does not produce duplicate rows for the same run
    EvidenceService.record_evidence(
        db=db_session,
        certification_id=run1.certification_id,
        source_system=SourceSystemEnum.ACE,
        evidence_type="VERSION_CONSISTENCY_AUDIT",
        evidence_data={"is_consistent": True, "retry_test": True},
        source_version=version,
    )
    ev_count_after = len(EvidenceService.get_evidence_for_certification(db_session, run1.certification_id))
    # Should update existing record rather than adding a duplicate
    assert ev_count_after == ev_count_1

    # Audit history from run 1 is completely preserved
    audit_trail_1 = EvidenceService.get_audit_trail(db_session, run1.certification_id)
    assert len(audit_trail_1) >= audit_count_1
