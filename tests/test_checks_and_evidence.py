"""Tests for Checks, Evidence, Integration Runs, and Audit Trail."""

from app.services.certification_service import CertificationService
from app.models.certification_check import CertificationCheck, CheckStatusEnum, CheckTypeEnum
from app.models.integration_run import IntegrationRun
from app.models.evidence import Evidence


def test_checks_endpoint_and_relationships(client, db_session):
    """Verify checks are created and linked to certification run."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-CHECKS-1",
        "name": "Check Agent",
        "version": "1.0.0",
    })

    res = client.post("/api/v1/certifications", json={
        "application_id": "APP-CHECKS-1",
        "version": "1.0.0",
        "commit_hash": "c001",
        "submission_id": "SUB-CHK-01",
    })
    cert_id = res.json()["certification_id"]

    # Execute pipeline
    CertificationService().execute_certification_pipeline(db_session, cert_id)

    # Call checks endpoint
    chk_res = client.get(f"/api/v1/certifications/{cert_id}/checks")
    assert chk_res.status_code == 200
    data = chk_res.json()
    assert data["certification_id"] == cert_id
    assert data["total_checks"] == 4

    check_types = {c["check_type"] for c in data["checks"]}
    assert "DOCUMENT" in check_types
    assert "QA" in check_types
    assert ("AGENT_RULES" in check_types or "RULE" in check_types)
    assert "VERSION" in check_types

    # Verify check fields
    for c in data["checks"]:
        assert c["check_id"].startswith("CHK-")
        assert c["status"] in ["PASS", "NOT_VERIFIED", "PENDING", "RUNNING"]
        assert c["started_at"] is not None
        assert c["completed_at"] is not None


def test_evidence_endpoint_and_provenance(client, db_session):
    """Verify evidence records contain check correlation, version, and source run ID."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-EVID-1",
        "name": "Evidence Agent",
        "version": "2.0.0",
    })

    res = client.post("/api/v1/certifications", json={
        "application_id": "APP-EVID-1",
        "version": "2.0.0",
    })
    cert_id = res.json()["certification_id"]

    CertificationService().execute_certification_pipeline(db_session, cert_id)

    ev_res = client.get(f"/api/v1/certifications/{cert_id}/evidence")
    assert ev_res.status_code == 200
    data = ev_res.json()
    assert data["certification_id"] == cert_id
    assert data["total_evidence"] >= 4

    for ev in data["evidence"]:
        assert ev["certification_id"] == cert_id
        assert ev["check_id"] is not None
        assert ev["source_system"] in ["MYBLOCKS_RAG", "MYBLOCKS_QA", "RULE_ENGINE", "ACE"]
        assert ev["evidence_data"] is not None


def test_integration_runs_correlation(db_session):
    """Verify external integration runs are recorded for cross-system correlation."""
    from app.services.application_service import ApplicationService
    from app.schemas.application import ApplicationCreate
    from app.schemas.certification import CertificationCreate

    ApplicationService.create_application(db_session, ApplicationCreate(
        application_id="APP-INTEG-1",
        name="Integ Agent",
        version="1.0.0",
    ))

    service = CertificationService()
    run = service.create_certification_run(db_session, CertificationCreate(
        application_id="APP-INTEG-1",
        version="1.0.0",
    ))

    service.execute_certification_pipeline(db_session, run.certification_id)

    integ_runs = (
        db_session.query(IntegrationRun)
        .filter(IntegrationRun.certification_id == run.certification_id)
        .all()
    )
    assert len(integ_runs) >= 3
    sources = {ir.source_system for ir in integ_runs}
    assert "MYBLOCKS_RAG" in sources
    assert "MYBLOCKS_QA" in sources
    assert "RULE_ENGINE" in sources

    for ir in integ_runs:
        assert ir.external_run_id is not None
        assert ir.external_application_id == "APP-INTEG-1"
        assert ir.external_version == "1.0.0"


def test_audit_trail_endpoint(client, db_session):
    """Verify complete audit trail is accessible via endpoint."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-AUDIT-1",
        "name": "Audit Agent",
        "version": "1.0.0",
    })
    res = client.post("/api/v1/certifications", json={"application_id": "APP-AUDIT-1"})
    cert_id = res.json()["certification_id"]

    CertificationService().execute_certification_pipeline(db_session, cert_id)

    audit_res = client.get(f"/api/v1/certifications/{cert_id}/audit")
    assert audit_res.status_code == 200
    data = audit_res.json()
    assert data["certification_id"] == cert_id
    assert data["total_events"] >= 6

    event_types = {e["event_type"] for e in data["events"]}
    assert "CERTIFICATION_CREATED" in event_types
    assert "CERTIFICATION_STARTED" in event_types
    assert "CHECK_CREATED" in event_types
    assert "CERTIFICATION_EVALUATED" in event_types
    assert "REMEDIATION_GENERATED" in event_types
    assert "CERTIFICATION_COMPLETED" in event_types
