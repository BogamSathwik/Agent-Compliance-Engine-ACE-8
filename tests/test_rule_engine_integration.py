"""Phase 5 Existing 9-Rule Agent Evaluation MCP Integration Tests.

Validates:
1. Unconfigured rule engine returns NOT_VERIFIED
2. Application/version mismatch returns NOT_VERIFIED
3. All 9 rules pass produces PASS
4. One mandatory rule fails produces FAIL and NOT_READY
5. Incomplete 9-rule response returns NOT_VERIFIED
"""

import httpx
from datetime import datetime, timezone
from app.models.certification import CertificationStatusEnum
from app.models.finding import FindingStatusEnum, FindingCategoryEnum
from app.models.evidence import Evidence
from app.models.integration_run import IntegrationRun
from app.integrations.contracts import (
    DocumentVerificationResult,
    QAVerificationResult,
    DocumentCategoryVerification,
    MANDATORY_17_DOC_CATEGORIES,
)
from app.integrations.rule_client import AgentRuleEvaluationClient
from app.mcp.client import ExternalMCPClient
from app.services.certification_service import CertificationService
from app.schemas.certification import CertificationCreate
from app.schemas.application import ApplicationCreate
from app.services.application_service import ApplicationService


def _get_passing_9_rules():
    return [
        {"rule_id": "RULE-1", "name": "Goal/objective", "passed": True, "status": "PASS", "reason": "Explicit goal defined"},
        {"rule_id": "RULE-2", "name": "AI/LLM reasoning", "passed": True, "status": "PASS", "reason": "Uses LLM reasoning core"},
        {"rule_id": "RULE-3", "name": "Ability to take actions", "passed": True, "status": "PASS", "reason": "Executes environmental actions"},
        {"rule_id": "RULE-4", "name": "Tool/function calling", "passed": True, "status": "PASS", "reason": "Configured tool definitions"},
        {"rule_id": "RULE-5", "name": "Autonomous decision making", "passed": True, "status": "PASS", "reason": "Self-directed decision loop"},
        {"rule_id": "RULE-6", "name": "Execution/agent loop", "passed": True, "status": "PASS", "reason": "Active iterative execution loop"},
        {"rule_id": "RULE-7", "name": "Environment/context", "passed": True, "status": "PASS", "reason": "Maintains context state"},
        {"rule_id": "RULE-8", "name": "Observation of results", "passed": True, "status": "PASS", "reason": "Monitors tool and step execution"},
        {"rule_id": "RULE-9", "name": "Adaptation/re-planning", "passed": True, "status": "PASS", "reason": "Adapts plan on failure"},
    ]


class MockPassingDocVerifier:
    def verify_application_documents(self, application_id: str, version: str):
        return DocumentVerificationResult(
            status=FindingStatusEnum.PASS,
            category=FindingCategoryEnum.DOCUMENT,
            required_count=17,
            verified_count=17,
            missing_categories=[],
            title="All 17 Documents Verified",
            description="All mandatory documentation categories verified.",
            external_run_id=f"DOC-RUN-{application_id}",
            external_application_id=application_id,
            external_version=version,
            category_verifications=[
                DocumentCategoryVerification(
                    category=cat,
                    requirement_id=f"DOC-{cat.replace('_', '-')}",
                    status=FindingStatusEnum.PASS,
                    title=f"Doc: {cat}",
                    description=f"{cat} verified",
                    raw_evidence={"category": cat, "verified": True},
                )
                for cat in MANDATORY_17_DOC_CATEGORIES
            ],
        )


class MockPassingQAVerifier:
    def verify_application_qa(self, application_id: str, version: str, commit_hash=None, submission_id=None):
        return QAVerificationResult(
            status=FindingStatusEnum.PASS,
            category=FindingCategoryEnum.QA,
            passed=True,
            pass_count=50,
            fail_count=0,
            critical_failures=0,
            external_run_id=f"QA-RUN-{application_id}",
            external_application_id=application_id,
            external_version=version,
            title="QA Test Suite Passed",
            description="All authoritative QA tests passed.",
        )


def test_rule_engine_unconfigured_returns_not_verified(db_session):
    """1. When 9-Rule MCP server/API is not configured, returns deterministic NOT_VERIFIED without fabricating success."""
    client = AgentRuleEvaluationClient(api_key=None, mcp_url=None)
    result = client.evaluate_agent_rules(application_id="APP-RULE-001", version="1.0.0")

    assert result.status == FindingStatusEnum.NOT_VERIFIED
    assert result.passed is False
    assert result.remediation is not None
    assert "not configured" in result.description.lower() or "requires" in result.description.lower()
    assert result.raw_evidence["integration"] == "RULE_ENGINE"


def test_rule_engine_version_mismatch_returns_not_verified(db_session):
    """2. If external Rule Engine reports results for a mismatched version (e.g. v1.7 vs v1.8), it must be rejected as NOT_VERIFIED."""
    def mock_mcp_transport(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "structuredContent": {
                        "application_id": "APP-RULE-VER",
                        "version": "1.7.0",  # Mismatched version (requested 1.8.0)
                        "run_id": "RULE-RUN-EXT-1122",
                        "status": "PASS",
                        "passed": True,
                        "rules": _get_passing_9_rules(),
                    }
                },
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_mcp_transport))
    mcp_client = ExternalMCPClient(base_url="https://mcp.rule-engine.test", http_client=mock_client)
    rule_verifier = AgentRuleEvaluationClient(mcp_url="https://mcp.rule-engine.test", mcp_client=mcp_client)

    result = rule_verifier.evaluate_agent_rules(
        application_id="APP-RULE-VER",
        version="1.8.0",
    )

    assert result.status == FindingStatusEnum.NOT_VERIFIED
    assert result.passed is False
    assert "mismatched target" in result.description.lower()

    # Through pipeline, cross-version Rule evidence must yield NOT_READY
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-RULE-VER", name="Rule Version App", version="1.8.0"),
    )
    service = CertificationService(rule_verifier=rule_verifier)
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id="APP-RULE-VER", version="1.8.0"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    assert completed.status == CertificationStatusEnum.NOT_READY.value


def test_rule_engine_all_9_rules_pass(db_session):
    """3. When all 9 mandatory rules pass for exact application/version, rule check passes and allows publication."""
    def mock_mcp_transport(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "result": {
                    "structuredContent": {
                        "application_id": "APP-RULE-PASS",
                        "version": "1.0.0",
                        "run_id": "RULE-RUN-9999",
                        "status": "PASS",
                        "passed": True,
                        "rules": _get_passing_9_rules(),
                        "confidence": 0.98,
                        "hash": "sha256-rule-pass-9999",
                    }
                },
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_mcp_transport))
    mcp_client = ExternalMCPClient(base_url="https://mcp.rule-engine.test", http_client=mock_client)
    rule_verifier = AgentRuleEvaluationClient(mcp_url="https://mcp.rule-engine.test", mcp_client=mcp_client)

    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-RULE-PASS", name="Rule Pass App", version="1.0.0"),
    )
    service = CertificationService(
        document_verifier=MockPassingDocVerifier(),
        qa_verifier=MockPassingQAVerifier(),
        rule_verifier=rule_verifier,
    )
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id="APP-RULE-PASS", version="1.0.0"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    # Rule check must PASS
    checks = service.get_checks(db_session, run.certification_id)
    rule_chk = next(c for c in checks if c.check_id == "CHK-RULE-001")
    assert rule_chk.status == "PASS"

    # Rule finding must PASS
    findings = service.get_findings(db_session, run.certification_id)
    rule_finding = next(f for f in findings if f.category == FindingCategoryEnum.RULE.value)
    assert rule_finding.status == "PASS"

    # Evidence and Integration Run persisted
    ev_records = db_session.query(Evidence).filter(Evidence.certification_id == run.certification_id).all()
    rule_ev = next(e for e in ev_records if e.source_system == "RULE_ENGINE")
    assert rule_ev.source_version == "1.0.0"
    assert rule_ev.source_run_id == "RULE-RUN-9999"

    int_runs = db_session.query(IntegrationRun).filter(IntegrationRun.certification_id == run.certification_id).all()
    rule_int = next(i for i in int_runs if i.source_system == "RULE_ENGINE")
    assert rule_int.status == "PASS"
    assert rule_int.external_version == "1.0.0"

    # All pass -> READY_TO_PUBLISH
    assert completed.status == CertificationStatusEnum.READY_TO_PUBLISH.value


def test_rule_engine_one_mandatory_rule_fails_produces_fail_and_not_ready(db_session):
    """4. When one mandatory rule fails (e.g. Execution/agent loop), status must be FAIL and certification NOT_READY."""
    rules_with_one_fail = _get_passing_9_rules()
    # Mark rule 6 (Execution/agent loop) as failed
    rules_with_one_fail[5]["passed"] = False
    rules_with_one_fail[5]["status"] = "FAIL"
    rules_with_one_fail[5]["reason"] = "Agent lacks autonomous execution loop; terminates prematurely."

    def mock_mcp_transport(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "3",
                "result": {
                    "structuredContent": {
                        "application_id": "APP-RULE-FAIL",
                        "version": "1.0.0",
                        "run_id": "RULE-RUN-FAIL-1",
                        "status": "FAIL",
                        "passed": False,
                        "rules": rules_with_one_fail,
                        "summary": "1 rule failed: Execution/agent loop.",
                    }
                },
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_mcp_transport))
    mcp_client = ExternalMCPClient(base_url="https://mcp.rule-engine.test", http_client=mock_client)
    rule_verifier = AgentRuleEvaluationClient(mcp_url="https://mcp.rule-engine.test", mcp_client=mcp_client)

    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-RULE-FAIL", name="Rule Fail App", version="1.0.0"),
    )
    service = CertificationService(rule_verifier=rule_verifier)
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id="APP-RULE-FAIL", version="1.0.0"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    # Must be NOT_READY (never BLOCKED or REJECTED)
    assert completed.status == CertificationStatusEnum.NOT_READY.value

    # Check and finding must be FAIL
    checks = service.get_checks(db_session, run.certification_id)
    rule_chk = next(c for c in checks if c.check_id == "CHK-RULE-001")
    assert rule_chk.status == "FAIL"

    findings = service.get_findings(db_session, run.certification_id)
    rule_finding = next(f for f in findings if f.category == FindingCategoryEnum.RULE.value)
    assert rule_finding.status == "FAIL"
    assert "Execution/agent loop" in rule_finding.description


def test_rule_engine_incomplete_response_returns_not_verified(db_session):
    """5. When response is missing any of the 9 mandatory rules, it must be rejected as NOT_VERIFIED."""
    # Only return 8 rules (missing rule 9: Adaptation/re-planning)
    incomplete_rules = _get_passing_9_rules()[:8]

    def mock_mcp_transport(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "4",
                "result": {
                    "structuredContent": {
                        "application_id": "APP-RULE-INCOMPLETE",
                        "version": "1.0.0",
                        "run_id": "RULE-RUN-INCOMPLETE",
                        "status": "PASS",
                        "passed": True,
                        "rules": incomplete_rules,
                    }
                },
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_mcp_transport))
    mcp_client = ExternalMCPClient(base_url="https://mcp.rule-engine.test", http_client=mock_client)
    rule_verifier = AgentRuleEvaluationClient(mcp_url="https://mcp.rule-engine.test", mcp_client=mcp_client)

    result = rule_verifier.evaluate_agent_rules(
        application_id="APP-RULE-INCOMPLETE",
        version="1.0.0",
    )

    assert result.status == FindingStatusEnum.NOT_VERIFIED
    assert result.passed is False
    assert "incomplete" in result.description.lower()
    assert "Adaptation/re-planning" in result.missing_rules

    # In pipeline, produces NOT_READY
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-RULE-INCOMPLETE", name="Rule Incomplete App", version="1.0.0"),
    )
    service = CertificationService(rule_verifier=rule_verifier)
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id="APP-RULE-INCOMPLETE", version="1.0.0"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    assert completed.status == CertificationStatusEnum.NOT_READY.value
    checks = service.get_checks(db_session, run.certification_id)
    rule_chk = next(c for c in checks if c.check_id == "CHK-RULE-001")
    assert rule_chk.status == "NOT_VERIFIED"
