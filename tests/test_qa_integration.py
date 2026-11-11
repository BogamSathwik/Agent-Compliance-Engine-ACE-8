"""Phase 4 MyBlocks QA integration smoke tests."""

import httpx
from datetime import datetime, timezone
from app.models.certification import CertificationStatusEnum
from app.models.certification_check import CertificationCheck
from app.models.finding import FindingStatusEnum, FindingCategoryEnum
from app.models.evidence import Evidence
from app.models.integration_run import IntegrationRun
from app.integrations.qa_client import MyBlocksQAClient
from app.services.certification_service import CertificationService
from app.schemas.certification import CertificationCreate
from app.schemas.application import ApplicationCreate
from app.services.application_service import ApplicationService


def test_qa_unconfigured_credentials_returns_not_verified(db_session):
    """When QA credentials/MCP are not configured, returns deterministic NOT_VERIFIED without fabricating success."""
    client = MyBlocksQAClient(api_key=None, mcp_url=None)
    result = client.verify_application_qa(application_id="APP-QA-001", version="1.0.0")

    assert result.status == FindingStatusEnum.NOT_VERIFIED
    assert result.passed is False
    assert result.remediation is not None
    assert "not configured" in result.description.lower() or "requires" in result.description.lower()
    assert result.raw_evidence["integration"] == "MYBLOCKS_QA"


def test_qa_cross_version_mismatch_rejected(db_session):
    """If QA reports results for a mismatched version (e.g. v1.7 vs v1.8), it must be rejected as NOT_VERIFIED."""
    def mock_transport(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "application_id": "APP-QA-VER",
                "version": "1.7.0",  # Mismatched version (requested 1.8.0)
                "qa_run_id": "QA-RUN-EXT-1122",
                "status": "PASS",
                "passed": True,
                "pass_count": 45,
                "fail_count": 0,
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_transport), base_url="https://mock.qa")
    qa_verifier = MyBlocksQAClient(http_client=mock_client)

    result = qa_verifier.verify_application_qa(
        application_id="APP-QA-VER",
        version="1.8.0",
    )

    assert result.status == FindingStatusEnum.NOT_VERIFIED
    assert result.passed is False
    assert "mismatched target" in result.description.lower()

    # Through pipeline, cross-version QA evidence must yield NOT_READY
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-QA-VER", name="QA Version App", version="1.8.0"),
    )
    service = CertificationService(qa_verifier=qa_verifier)
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id="APP-QA-VER", version="1.8.0"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    assert completed.status == CertificationStatusEnum.NOT_READY.value


def test_qa_explicit_failure_produces_fail_and_not_ready(db_session):
    """When MyBlocks QA reports test failures, status must be FAIL and certification NOT_READY."""
    def mock_transport(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "application_id": "APP-QA-FAIL",
                "version": "2.0.0",
                "qa_run_id": "QA-RUN-FAILED-99",
                "status": "FAIL",
                "passed": False,
                "pass_count": 40,
                "fail_count": 5,
                "critical_failures": 2,
                "summary": "5 tests failed, 2 critical security issues detected.",
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_transport), base_url="https://mock.qa")
    qa_verifier = MyBlocksQAClient(http_client=mock_client)

    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-QA-FAIL", name="QA Failure App", version="2.0.0"),
    )
    service = CertificationService(qa_verifier=qa_verifier)
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id="APP-QA-FAIL", version="2.0.0"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    assert completed.status == CertificationStatusEnum.NOT_READY.value

    # Check that QA check and finding have status FAIL
    checks = service.get_checks(db_session, run.certification_id)
    qa_chk = next(c for c in checks if c.check_type == "QA")
    assert qa_chk.status == "FAIL"

    findings = service.get_findings(db_session, run.certification_id)
    qa_finding = next(f for f in findings if f.category == FindingCategoryEnum.QA.value)
    assert qa_finding.status == "FAIL"
    assert "5 tests failed" in qa_finding.description


def test_qa_pass_persists_evidence_and_integration_run(db_session):
    """When MyBlocks QA reports full pass for exact version, QA check passes and evidence is stored."""
    def mock_transport(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "application_id": "APP-QA-PASS",
                "version": "1.0.0",
                "qa_run_id": "QA-RUN-PASS-777",
                "status": "PASS",
                "passed": True,
                "pass_count": 88,
                "fail_count": 0,
                "critical_failures": 0,
                "qa_score": 98.5,
                "confidence": 0.99,
                "hash": "sha256-qa-pass-digest-777",
                "source_reference": "qa-report://myblocks/APP-QA-PASS/1.0.0/run-777",
                "summary": "All 88 QA test suites passed with zero regressions.",
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_transport), base_url="https://mock.qa")
    qa_verifier = MyBlocksQAClient(http_client=mock_client)

    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-QA-PASS", name="QA Pass App", version="1.0.0"),
    )
    service = CertificationService(qa_verifier=qa_verifier)
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id="APP-QA-PASS", version="1.0.0"),
    )
    service.execute_certification_pipeline(db_session, run.certification_id)

    # QA check must PASS
    checks = service.get_checks(db_session, run.certification_id)
    qa_chk = next(c for c in checks if c.check_type == "QA")
    assert qa_chk.status == "PASS"

    # QA finding must PASS
    findings = service.get_findings(db_session, run.certification_id)
    qa_finding = next(f for f in findings if f.category == FindingCategoryEnum.QA.value)
    assert qa_finding.status == "PASS"

    # QA integration run must be recorded
    integ_runs = (
        db_session.query(IntegrationRun)
        .filter(
            IntegrationRun.certification_id == run.certification_id,
            IntegrationRun.source_system == "MYBLOCKS_QA",
        )
        .all()
    )
    assert len(integ_runs) == 1
    assert integ_runs[0].external_run_id == "QA-RUN-PASS-777"
    assert integ_runs[0].external_application_id == "APP-QA-PASS"
    assert integ_runs[0].external_version == "1.0.0"
    assert integ_runs[0].status == "PASS"

    # Evidence record must be recorded
    qa_evidence = (
        db_session.query(Evidence)
        .filter(
            Evidence.certification_id == run.certification_id,
            Evidence.source_system == "MYBLOCKS_QA",
        )
        .all()
    )
    assert len(qa_evidence) == 1
    assert qa_evidence[0].source_run_id == "QA-RUN-PASS-777"
    assert qa_evidence[0].source_version == "1.0.0"
    assert qa_evidence[0].confidence == 0.99
    assert qa_evidence[0].hash == "sha256-qa-pass-digest-777"
    assert qa_evidence[0].source_reference == "qa-report://myblocks/APP-QA-PASS/1.0.0/run-777"
