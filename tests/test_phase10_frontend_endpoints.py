"""Tests for Phase 10 frontend endpoints and static serving."""

import pytest
from app.models.application import Application
from app.models.certification import CertificationRun, CertificationStatusEnum


def test_list_certifications_endpoint(client, db_session):
    """GET /api/v1/certifications returns list of runs with findings summaries."""
    app_record = Application(
        application_id="APP-FE-TEST",
        name="Frontend Test App",
        current_version="1.0.0",
        application_type="AI_AGENT",
    )
    db_session.add(app_record)
    db_session.commit()

    run1 = CertificationRun(
        certification_id="CERT-FE-001",
        application_id="APP-FE-TEST",
        application_version="1.0.0",
        status=CertificationStatusEnum.READY_TO_PUBLISH.value,
    )
    run2 = CertificationRun(
        certification_id="CERT-FE-002",
        application_id="APP-FE-TEST",
        application_version="1.0.0",
        status=CertificationStatusEnum.NOT_READY.value,
    )
    db_session.add_all([run1, run2])
    db_session.commit()

    res = client.get("/api/v1/certifications")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    ids = [r["certification_id"] for r in data]
    assert "CERT-FE-001" in ids
    assert "CERT-FE-002" in ids

    # Filter by status
    res_filtered = client.get("/api/v1/certifications?status=READY_TO_PUBLISH")
    assert res_filtered.status_code == 200
    filtered_ids = [r["certification_id"] for r in res_filtered.json()]
    assert "CERT-FE-001" in filtered_ids
    assert "CERT-FE-002" not in filtered_ids


def test_list_application_certification_runs_endpoint(client, db_session):
    """GET /api/v1/applications/{app_id}/certification-runs returns history for app."""
    app_record = Application(
        application_id="APP-FE-HIST",
        name="History Test App",
        current_version="1.0.0",
        application_type="AI_AGENT",
    )
    db_session.add(app_record)
    db_session.commit()

    run = CertificationRun(
        certification_id="CERT-FE-HIST-01",
        application_id="APP-FE-HIST",
        application_version="1.0.0",
        status=CertificationStatusEnum.READY_TO_PUBLISH.value,
    )
    db_session.add(run)
    db_session.commit()

    res = client.get("/api/v1/applications/APP-FE-HIST/certification-runs")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["certification_id"] == "CERT-FE-HIST-01"


def test_frontend_static_serving(client):
    """GET / serves the frontend index.html."""
    res = client.get("/")
    assert res.status_code == 200
    assert "ACE" in res.text
