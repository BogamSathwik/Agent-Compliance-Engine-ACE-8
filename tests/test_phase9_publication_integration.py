"""Phase 9: AgentGen Pro Publication Integration Tests.

Validates the complete publication workflow:
1. NOT_READY application cannot be published.
2. READY_TO_PUBLISH application can request publication.
3. External confirmation is required before marking PUBLISHED.
4. Duplicate requests do not create duplicate publications (idempotency).
5. Application/version mismatch prevents publication.
6. Timeout or ambiguous external response does not claim success.
7. Failed external publication is recorded and can be safely retried.
8. REST and MCP publication paths enforce identical policy.
"""

from typing import Any, Dict, Optional
import pytest

from app.core.exceptions import PublicationEligibilityError
from app.integrations.contracts import (
    DocumentCategoryVerification,
    DocumentVerificationResult,
    FindingCategoryEnum,
    FindingStatusEnum,
    QAVerificationResult,
    RuleEvaluationResult,
    SingleRuleEvaluation,
    MANDATORY_17_DOC_CATEGORIES,
    MANDATORY_9_AGENT_RULES,
)
from app.integrations.publication_client import (
    ExternalPublicationResult,
    PublicationClientProtocol,
)
from app.models.certification import CertificationRun, CertificationStatusEnum
from app.models.publication import PublicationRecord, PublicationStatusEnum
from app.schemas.application import ApplicationCreate
from app.schemas.certification import CertificationCreate
from app.services.application_service import ApplicationService
from app.services.certification_service import CertificationService
from app.services.publication_service import PublicationService
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


class MockPublicationClient(PublicationClientProtocol):
    """Configurable mock client simulating AgentGen Pro publication responses."""

    def __init__(
        self,
        request_func=None,
        status_func=None,
    ):
        self.request_func = request_func or (lambda **kw: ExternalPublicationResult(
            status="PUBLISHED",
            external_publication_id="EXT-PUB-MOCK-001",
            confirmation_details={"agentgen_deployment_id": "DEP-999"},
        ))
        self.status_func = status_func or (lambda **kw: ExternalPublicationResult(
            status="PUBLISHED",
            external_publication_id="EXT-PUB-MOCK-001",
        ))

    def request_publication(self, **kwargs) -> ExternalPublicationResult:
        return self.request_func(**kwargs)

    def check_publication_status(self, **kwargs) -> ExternalPublicationResult:
        return self.status_func(**kwargs)


def _certify_application(db_session, app_id: str, version: str, should_pass: bool = True):
    """Helper to run a full certification pipeline producing either READY_TO_PUBLISH or NOT_READY."""
    doc_res = _build_passing_doc_result(app_id, version) if should_pass else _build_failing_doc_result(app_id, version)
    service = CertificationService(
        document_verifier=MockDocVerifier(lambda a, v: doc_res),
        qa_verifier=MockQAVerifier(lambda a, v: _build_passing_qa_result(a, v)),
        rule_verifier=MockRuleVerifier(lambda a, v: _build_passing_rule_result(a, v)),
    )
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id=app_id, version=version, submission_id=f"SUB-{app_id}"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)
    return completed


# =========================================================================
# Phase 9 Verification Tests
# =========================================================================

def test_phase9_not_ready_application_cannot_be_published(client, db_session):
    """1. NOT_READY application cannot request publication via service, REST, or MCP."""
    app_id = "APP-P9-NOTREADY"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Not Ready App", version=version),
    )
    # Produce NOT_READY run
    run = _certify_application(db_session, app_id, version, should_pass=False)
    assert run.status == CertificationStatusEnum.NOT_READY.value

    # Service call must raise PublicationEligibilityError
    pub_service = PublicationService(publication_client=MockPublicationClient())
    with pytest.raises(PublicationEligibilityError) as exc_info:
        pub_service.request_publication(db_session, app_id, version)
    assert "not eligible for publication" in str(exc_info.value)

    # REST call must return 400
    res = client.post(f"/api/v1/applications/{app_id}/publish", json={"version": version})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "PUBLICATION_INELIGIBLE"

    # MCP call via call_tool directly raises PublicationEligibilityError
    with pytest.raises(PublicationEligibilityError):
        ACEMCPServer.call_tool("request_publication", {"application_id": app_id, "version": version}, db_session)

    # MCP call via handle_jsonrpc reports isError: True
    mcp_jsonrpc = ACEMCPServer.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "request_publication", "arguments": {"application_id": app_id, "version": version}},
        },
        db_session,
    )
    assert mcp_jsonrpc["result"]["isError"] is True



def test_phase9_ready_to_publish_application_can_request_publication(db_session):
    """2. READY_TO_PUBLISH application can request publication and create bound record."""
    app_id = "APP-P9-READY"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Ready App", version=version),
    )
    run = _certify_application(db_session, app_id, version, should_pass=True)
    assert run.status == CertificationStatusEnum.READY_TO_PUBLISH.value

    mock_client = MockPublicationClient()
    pub_service = PublicationService(publication_client=mock_client)

    pub_record = pub_service.request_publication(db_session, app_id, version)
    assert pub_record.publication_id.startswith("PUB-")
    assert pub_record.application_id == app_id
    assert pub_record.application_version == version
    assert pub_record.certification_id == run.certification_id
    assert pub_record.status == PublicationStatusEnum.PUBLISHED.value
    assert pub_record.external_publication_id == "EXT-PUB-MOCK-001"
    assert pub_record.confirmed_at is not None


def test_phase9_external_confirmation_is_required_before_marking_published(client, db_session):
    """3. Async request remains PUBLICATION_REQUESTED until authoritative external confirmation."""
    app_id = "APP-P9-ASYNC"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Async App", version=version),
    )
    run = _certify_application(db_session, app_id, version, should_pass=True)
    assert run.status == CertificationStatusEnum.READY_TO_PUBLISH.value

    # Mock client simulating in-flight async request (staged, not yet published)
    async_client = MockPublicationClient(
        request_func=lambda **kw: ExternalPublicationResult(
            status="REQUESTED",
            external_publication_id="EXT-ASYNC-100",
            confirmation_details={"queue_position": 1},
        )
    )
    pub_service = PublicationService(publication_client=async_client)
    record = pub_service.request_publication(db_session, app_id, version)

    # Must NOT claim publication succeeded merely because request was sent!
    assert record.status == PublicationStatusEnum.PUBLICATION_REQUESTED.value
    assert record.confirmed_at is None

    # Simulate webhook callback from AgentGen Pro with authoritative confirmation
    webhook_res = client.post(
        "/api/v1/webhooks/agentgen",
        json={
            "event_type": "PUBLICATION_CONFIRMED",
            "source": "AGENTGEN_PRO",
            "payload": {
                "publication_id": record.publication_id,
                "external_publication_id": "EXT-ASYNC-100",
                "status": "PUBLISHED",
                "marketplace_url": "https://agents.myblocks.in/app-p9-async",
            },
        },
    )
    assert webhook_res.status_code == 200
    assert webhook_res.json()["publication_status"] == "PUBLISHED"

    # Verify DB record is now authoritatively PUBLISHED
    db_session.refresh(record)
    assert record.status == PublicationStatusEnum.PUBLISHED.value
    assert record.confirmed_at is not None


def test_phase9_duplicate_requests_do_not_create_duplicate_publications(db_session):
    """4. Duplicate publication requests are idempotent and do not create duplicate publications."""
    app_id = "APP-P9-IDEMP"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Idempotent App", version=version),
    )
    _certify_application(db_session, app_id, version, should_pass=True)

    pub_service = PublicationService(publication_client=MockPublicationClient())

    # Request 1
    rec1 = pub_service.request_publication(db_session, app_id, version)
    assert rec1.status == PublicationStatusEnum.PUBLISHED.value

    # Request 2 for the exact same version
    rec2 = pub_service.request_publication(db_session, app_id, version)
    assert rec1.publication_id == rec2.publication_id

    # Total records in DB must be exactly 1
    total_pubs = (
        db_session.query(PublicationRecord)
        .filter(PublicationRecord.application_id == app_id)
        .count()
    )
    assert total_pubs == 1


def test_phase9_application_version_mismatch_prevents_publication(db_session):
    """5. Never publish an older or different version based on a certified run for another version."""
    app_id = "APP-P9-MISMATCH"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Mismatch App", version="1.0.0"),
    )
    # Certify version 1.0.0
    _certify_application(db_session, app_id, "1.0.0", should_pass=True)

    pub_service = PublicationService(publication_client=MockPublicationClient())

    # Attempt to publish uncertified version 2.0.0
    with pytest.raises(PublicationEligibilityError) as exc_info:
        pub_service.request_publication(db_session, app_id, "2.0.0")
    assert "No certification run exists" in str(exc_info.value) or "version" in str(exc_info.value)


def test_phase9_timeout_or_ambiguous_external_response_does_not_claim_success(db_session):
    """6. Timeout or ambiguous external response records PUBLICATION_STATUS_UNKNOWN, not PUBLISHED."""
    app_id = "APP-P9-TIMEOUT"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Timeout App", version=version),
    )
    _certify_application(db_session, app_id, version, should_pass=True)

    timeout_client = MockPublicationClient(
        request_func=lambda **kw: ExternalPublicationResult(
            status="UNKNOWN",
            is_timeout=True,
            error_code="TIMEOUT",
            error_message="Gateway Timeout (504)",
        )
    )
    pub_service = PublicationService(publication_client=timeout_client)

    rec = pub_service.request_publication(db_session, app_id, version)
    assert rec.status == PublicationStatusEnum.PUBLICATION_STATUS_UNKNOWN.value
    assert rec.confirmed_at is None
    assert rec.error_code == "TIMEOUT"


def test_phase9_failed_external_publication_is_recorded_and_safely_retried(db_session):
    """7. Failed publication records failure details and permits safe retries."""
    app_id = "APP-P9-RETRY"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Retry App", version=version),
    )
    _certify_application(db_session, app_id, version, should_pass=True)

    # Attempt 1: Fails
    failing_client = MockPublicationClient(
        request_func=lambda **kw: ExternalPublicationResult(
            status="FAILED",
            error_code="DEPLOYMENT_FAILURE",
            error_message="Worker cluster capacity exceeded",
        )
    )
    service1 = PublicationService(publication_client=failing_client)
    rec1 = service1.request_publication(db_session, app_id, version)
    assert rec1.status == PublicationStatusEnum.PUBLICATION_FAILED.value
    assert rec1.error_code == "DEPLOYMENT_FAILURE"

    # Query failure details
    failure = service1.get_failure_details(db_session, app_id, version)
    assert failure is not None
    assert failure.error_code == "DEPLOYMENT_FAILURE"
    assert failure.retry_count == 0

    # Attempt 2: Retry succeeds
    succeeding_client = MockPublicationClient(
        request_func=lambda **kw: ExternalPublicationResult(
            status="PUBLISHED",
            external_publication_id="EXT-PUB-RETRY-SUCCESS",
            confirmation_details={"cluster": "us-east-1"},
        )
    )
    service2 = PublicationService(publication_client=succeeding_client)
    rec2 = service2.request_publication(db_session, app_id, version)
    assert rec2.status == PublicationStatusEnum.PUBLISHED.value
    assert rec2.retry_count == 1
    assert rec2.external_publication_id == "EXT-PUB-RETRY-SUCCESS"


def test_phase9_rest_and_mcp_publication_paths_enforce_identical_policy(client, db_session):
    """8. REST API and MCP tool enforce identical publication policy and safeguards."""
    app_id = "APP-P9-IDENTICAL"
    version = "1.0.0"
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Identical App", version=version),
    )

    # 1. While uncertified: both reject
    rest_res = client.post(f"/api/v1/applications/{app_id}/publish", json={"version": version})
    assert rest_res.status_code == 400

    mcp_call = ACEMCPServer.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "request_publication", "arguments": {"application_id": app_id, "version": version}},
        },
        db_session,
    )
    assert mcp_call["result"]["isError"] is True

    # 2. After certifying: both succeed
    _certify_application(db_session, app_id, version, should_pass=True)

    # Call via MCP
    mcp_call2 = ACEMCPServer.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "request_publication", "arguments": {"application_id": app_id, "version": version}},
        },
        db_session,
    )
    assert mcp_call2["result"]["isError"] is False
    mcp_data = mcp_call2["result"]["structuredContent"]
    assert mcp_data["status"] in ("PUBLISHED", "PUBLICATION_REQUESTED", "PUBLICATION_FAILED")

    # REST status check reports identical publication status
    status_res = client.get(f"/api/v1/applications/{app_id}/publication-status?version={version}")
    assert status_res.status_code == 200
    assert status_res.json()["is_eligible_for_publication"] is True
