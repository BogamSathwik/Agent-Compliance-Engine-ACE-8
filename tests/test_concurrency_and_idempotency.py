"""Tests for Concurrency Protection, Idempotency, and State Transitions."""

import pytest
from app.services.certification_service import CertificationService, InvalidStatusTransitionError
from app.models.certification import CertificationRun, CertificationStatusEnum


def test_idempotent_duplicate_submission(client):
    """Submitting duplicate certification request with same submission_id returns existing active run."""
    client.post("/api/v1/applications", json={
        "application_id": "APP-IDEMP-1",
        "name": "Idempotent Agent",
        "version": "1.0.0",
    })

    payload = {
        "application_id": "APP-IDEMP-1",
        "version": "1.0.0",
        "commit_hash": "a1b2c3d",
        "submission_id": "SUB-IDEMP-999",
    }

    # First submission
    res1 = client.post("/api/v1/certifications", json=payload)
    assert res1.status_code == 202
    cert_id_1 = res1.json()["certification_id"]
    assert res1.json()["submission_id"] == "SUB-IDEMP-999"

    # Second identical submission
    res2 = client.post("/api/v1/certifications", json=payload)
    assert res2.status_code == 202
    cert_id_2 = res2.json()["certification_id"]

    # Must return the same active certification run rather than creating a duplicate
    assert cert_id_1 == cert_id_2


def test_controlled_status_transitions(db_session):
    """A certification cannot transition from completed status back to RUNNING."""
    from app.services.application_service import ApplicationService
    from app.schemas.application import ApplicationCreate
    from app.schemas.certification import CertificationCreate

    ApplicationService.create_application(db_session, ApplicationCreate(
        application_id="APP-TRANS-1",
        name="Transition Agent",
        version="1.0.0",
    ))

    service = CertificationService()
    run = service.create_certification_run(db_session, CertificationCreate(
        application_id="APP-TRANS-1",
        version="1.0.0",
    ))

    # Run once to completion (transitions QUEUED -> RUNNING -> NOT_READY)
    service.execute_certification_pipeline(db_session, run.certification_id)

    # Attempting to execute pipeline on an already completed run must raise InvalidStatusTransitionError
    with pytest.raises(InvalidStatusTransitionError):
        service.execute_certification_pipeline(db_session, run.certification_id)
