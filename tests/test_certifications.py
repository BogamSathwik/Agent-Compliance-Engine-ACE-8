"""Tests for Certification API endpoints."""


def test_create_certification(client):
    """POST /api/v1/certifications queues run and returns certification_id."""
    # 1. Register application first
    client.post("/api/v1/applications", json={
        "application_id": "APP-CERT-1",
        "name": "Audit Bot",
        "version": "1.0.0",
    })

    # 2. Request certification
    payload = {
        "application_id": "APP-CERT-1",
        "version": "1.0.0",
        "commit_hash": "f4b3a21",
    }
    response = client.post("/api/v1/certifications", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["certification_id"].startswith("CERT-")
    assert data["application_id"] == "APP-CERT-1"
    assert data["status"] == "QUEUED"

    # Verify background Celery job was queued
    assert data["certification_id"] in client.queued_tasks


def test_create_certification_invalid_application(client):
    """POST /api/v1/certifications for unknown application must return 404."""
    payload = {
        "application_id": "APP-DOES-NOT-EXIST",
        "version": "1.0.0",
    }
    response = client.post("/api/v1/certifications", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "APPLICATION_NOT_FOUND"


def test_create_duplicate_active_certification(client):
    """POST /api/v1/certifications returns 409 if certification is already active."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-CERT-DUP",
        "name": "Single Worker App",
        "version": "1.0.0",
    })

    payload = {"application_id": "APP-CERT-DUP", "version": "1.0.0"}
    res1 = client.post("/api/v1/certifications", json=payload)
    assert res1.status_code == 202

    # Second run while first is still QUEUED
    res2 = client.post("/api/v1/certifications", json=payload)
    assert res2.status_code == 409
    data = res2.json()
    assert data["error"]["code"] == "CERTIFICATION_ALREADY_RUNNING"


def test_get_certification(client):
    """GET /api/v1/certifications/{id} returns run metadata and findings summary."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-GET-CERT",
        "name": "Getter App",
        "version": "1.0.0",
    })

    start_res = client.post("/api/v1/certifications", json={
        "application_id": "APP-GET-CERT",
        "version": "1.0.0",
    })
    cert_id = start_res.json()["certification_id"]

    response = client.get(f"/api/v1/certifications/{cert_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["certification_id"] == cert_id
    assert data["application_id"] == "APP-GET-CERT"
    assert data["status"] == "QUEUED"
    assert "findings_summary" in data
    assert data["findings_summary"]["total"] == 0


def test_get_certification_not_found(client):
    """GET /api/v1/certifications/{id} for non-existent ID returns 404."""
    response = client.get("/api/v1/certifications/CERT-NON-EXISTENT")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CERTIFICATION_NOT_FOUND"


def test_get_findings_empty_on_queued(client):
    """GET /api/v1/certifications/{id}/findings returns empty list before worker runs."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-FINDINGS-1",
        "name": "Findings App",
        "version": "1.0.0",
    })
    res = client.post("/api/v1/certifications", json={"application_id": "APP-FINDINGS-1"})
    cert_id = res.json()["certification_id"]

    response = client.get(f"/api/v1/certifications/{cert_id}/findings")
    assert response.status_code == 200
    data = response.json()
    assert data["certification_id"] == cert_id
    assert data["total_findings"] == 0
    assert data["findings"] == []


def test_get_findings_after_pipeline_run(client, db_session):
    """GET /api/v1/certifications/{id}/findings returns all findings and remediation after execution."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-FINDINGS-POST",
        "name": "Remediation App",
        "version": "1.0.0",
    })
    res = client.post("/api/v1/certifications", json={"application_id": "APP-FINDINGS-POST"})
    cert_id = res.json()["certification_id"]

    # Execute pipeline
    from app.services.certification_service import CertificationService
    CertificationService().execute_certification_pipeline(db_session, cert_id)

    # Fetch findings
    response = client.get(f"/api/v1/certifications/{cert_id}/findings")
    assert response.status_code == 200
    data = response.json()
    assert data["total_findings"] == 20
    not_verified_count = 0
    for finding in data["findings"]:
        assert finding["certification_id"] == cert_id
        if finding["status"] == "NOT_VERIFIED":
            not_verified_count += 1
            assert finding["remediation"] is not None
            assert len(finding["remediation"]) > 10
    assert not_verified_count == 19


def test_application_status_after_pipeline_run(client, db_session):
    """GET /api/v1/applications/{id}/status returns latest certification summary after execution."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-STATUS-POST",
        "name": "Status Check App",
        "version": "1.0.0",
    })
    res = client.post("/api/v1/certifications", json={"application_id": "APP-STATUS-POST"})
    cert_id = res.json()["certification_id"]

    from app.services.certification_service import CertificationService
    CertificationService().execute_certification_pipeline(db_session, cert_id)

    response = client.get("/api/v1/applications/APP-STATUS-POST/status")
    assert response.status_code == 200
    data = response.json()
    assert data["application_id"] == "APP-STATUS-POST"
    assert data["latest_certification"] is not None
    assert data["latest_certification"]["certification_id"] == cert_id
    assert data["latest_certification"]["status"] == "NOT_READY"
    assert data["latest_certification"]["findings_summary"]["total"] == 20


