"""Phase 3 MyBlocks RAG integration smoke tests."""

import httpx
from datetime import datetime, timezone
from app.models.requirement import Requirement
from app.models.certification import CertificationStatusEnum
from app.models.finding import FindingStatusEnum
from app.models.evidence import Evidence
from app.models.integration_run import IntegrationRun
from app.integrations.contracts import MANDATORY_17_DOC_CATEGORIES
from app.integrations.rag_client import MyBlocksRAGClient
from app.services.certification_service import CertificationService
from app.schemas.certification import CertificationCreate
from app.schemas.application import ApplicationCreate
from app.services.application_service import ApplicationService


def test_requirements_table_seeded_with_17_categories(db_session):
    """Verify that the requirements table contains all 17 mandatory document categories."""
    reqs = db_session.query(Requirement).all()
    req_ids = {r.requirement_id for r in reqs}
    categories = {r.category for r in reqs}

    assert len(MANDATORY_17_DOC_CATEGORIES) == 17
    for cat in MANDATORY_17_DOC_CATEGORIES:
        expected_id = f"DOC-{cat.replace('_', '-')}"
        assert expected_id in req_ids
        assert cat in categories

    for r in reqs:
        assert r.mandatory is True
        assert r.active is True
        assert r.policy_version == "v1.0"


def test_rag_unconfigured_credentials_returns_not_verified(db_session):
    """When RAG credentials or external contract is not configured, returns deterministic NOT_VERIFIED."""
    client = MyBlocksRAGClient(api_key=None)
    result = client.verify_application_documents(application_id="APP-TEST-001", version="1.0.0")

    assert result.status == FindingStatusEnum.NOT_VERIFIED
    assert result.required_count == 17
    assert result.verified_count == 0
    assert len(result.missing_categories) == 17
    assert len(result.category_verifications) == 17

    # Verify no fake chunks or fake success fabricated
    for cat_ver in result.category_verifications:
        assert cat_ver.status == FindingStatusEnum.NOT_VERIFIED
        assert "not verified" in cat_ver.description.lower() or "requires" in cat_ver.description.lower()
        assert cat_ver.remediation is not None


def test_rag_cross_version_mismatch_rejected(db_session):
    """If RAG reports evidence for a different version, it must be marked NOT_VERIFIED and NOT_READY."""
    # Transport that simulates RAG returning mismatched version 1.0.0 when 2.0.0 was requested
    def mock_transport(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "application_id": "APP-VERSION-TEST",
                "version": "1.0.0",  # Mismatched version!
                "run_id": "RAG-EXT-9988",
                "categories": {
                    cat: {"status": "PASS", "verified": True, "confidence": 0.95}
                    for cat in MANDATORY_17_DOC_CATEGORIES
                },
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_transport), base_url="https://mock.rag")
    rag_verifier = MyBlocksRAGClient(http_client=mock_client)

    result = rag_verifier.verify_application_documents(
        application_id="APP-VERSION-TEST",
        version="2.0.0",
    )

    # Must reject cross-version evidence
    assert result.status == FindingStatusEnum.NOT_VERIFIED
    assert "mismatched target" in result.description.lower()

    # When executed through pipeline, overall status must evaluate to NOT_READY
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-VERSION-TEST", name="Version App", version="2.0.0"),
    )
    service = CertificationService(document_verifier=rag_verifier)
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id="APP-VERSION-TEST", version="2.0.0"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    assert completed.status == CertificationStatusEnum.NOT_READY.value


def test_rag_verified_documents_pipeline_and_evidence(db_session):
    """When RAG successfully verifies all 17 categories for exact version, evidence is captured and check passes."""
    def mock_transport(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "application_id": "APP-RAG-SUCCESS",
                "version": "3.1.0",
                "run_id": "RAG-RUN-SUCCESS-101",
                "categories": {
                    cat: {
                        "status": "PASS",
                        "verified": True,
                        "confidence": 0.98,
                        "source_reference": f"rag-doc://APP-RAG-SUCCESS/3.1.0/{cat}.pdf",
                        "hash": f"sha256-{cat.lower()}-verified",
                        "summary": f"Verified {cat} specifications and governance invariants.",
                    }
                    for cat in MANDATORY_17_DOC_CATEGORIES
                },
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_transport), base_url="https://mock.rag")
    rag_verifier = MyBlocksRAGClient(http_client=mock_client)

    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-RAG-SUCCESS", name="Success App", version="3.1.0"),
    )
    service = CertificationService(document_verifier=rag_verifier)
    run = service.create_certification_run(
        db_session,
        CertificationCreate(application_id="APP-RAG-SUCCESS", version="3.1.0"),
    )
    completed = service.execute_certification_pipeline(db_session, run.certification_id)

    # Document check must PASS
    doc_checks = service.get_checks(db_session, run.certification_id)
    doc_chk = next(c for c in doc_checks if c.check_type == "DOCUMENT")
    assert doc_chk.status == "PASS"

    # All 17 document findings must PASS
    findings = service.get_findings(db_session, run.certification_id)
    doc_findings = [f for f in findings if f.category == "DOCUMENT"]
    assert len(doc_findings) == 17
    for f in doc_findings:
        assert f.status == "PASS"
        assert f.requirement_id.startswith("DOC-")

    # Integration run must correlate external RAG run ID
    integ_runs = (
        db_session.query(IntegrationRun)
        .filter(
            IntegrationRun.certification_id == run.certification_id,
            IntegrationRun.source_system == "MYBLOCKS_RAG",
        )
        .all()
    )
    assert len(integ_runs) == 1
    assert integ_runs[0].external_run_id == "RAG-RUN-SUCCESS-101"
    assert integ_runs[0].external_application_id == "APP-RAG-SUCCESS"
    assert integ_runs[0].external_version == "3.1.0"
    assert integ_runs[0].status == "PASS"

    # Evidence records must contain confidence, hash, and source references
    doc_evidence = (
        db_session.query(Evidence)
        .filter(
            Evidence.certification_id == run.certification_id,
            Evidence.source_system == "MYBLOCKS_RAG",
        )
        .all()
    )
    assert len(doc_evidence) == 17
    for ev in doc_evidence:
        assert ev.confidence == 0.98
        assert ev.hash.startswith("sha256-")
        assert ev.source_reference.startswith("rag-doc://APP-RAG-SUCCESS/3.1.0/")
        assert ev.source_run_id == "RAG-RUN-SUCCESS-101"
