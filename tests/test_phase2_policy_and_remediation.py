"""Tests for Phase 2 PolicyEngine and RemediationService."""

from app.core.context import CertificationContext
from app.services.policy_engine import PolicyEngine
from app.services.remediation_service import RemediationService
from app.models.certification import CertificationStatusEnum
from app.models.certification_check import CertificationCheck, CheckStatusEnum, CheckTypeEnum
from app.models.finding import CertificationFinding, FindingStatusEnum, FindingSeverityEnum


def test_policy_engine_all_pass_ready_to_publish():
    """When all mandatory checks and findings are PASS, policy evaluates to READY_TO_PUBLISH."""
    context = CertificationContext("CERT-P1", "APP-1", "1.0.0")

    checks = [
        CertificationCheck(certification_id="CERT-P1", check_id="CHK-1", check_type="DOCUMENT", check_name="Docs", source_system="MYBLOCKS_RAG", status=CheckStatusEnum.PASS.value),
        CertificationCheck(certification_id="CERT-P1", check_id="CHK-2", check_type="QA", check_name="QA", source_system="MYBLOCKS_QA", status=CheckStatusEnum.PASS.value),
        CertificationCheck(certification_id="CERT-P1", check_id="CHK-3", check_type="RULE", check_name="Rules", source_system="RULE_ENGINE", status=CheckStatusEnum.PASS.value),
    ]

    findings = [
        CertificationFinding(certification_id="CERT-P1", category="DOCUMENT", status=FindingStatusEnum.PASS.value, severity="INFO", title="Docs verified", description="17/17 verified"),
        CertificationFinding(certification_id="CERT-P1", category="QA", status=FindingStatusEnum.PASS.value, severity="INFO", title="QA pass", description="All passed"),
        CertificationFinding(certification_id="CERT-P1", category="RULE", status=FindingStatusEnum.PASS.value, severity="INFO", title="Rule pass", description="All passed"),
    ]

    status = PolicyEngine.evaluate_certification(context, checks, findings)
    assert status == CertificationStatusEnum.READY_TO_PUBLISH


def test_policy_engine_check_error_evaluates_to_error():
    """A fatal check execution error evaluates to ERROR."""
    context = CertificationContext("CERT-P2", "APP-1", "1.0.0")

    checks = [
        CertificationCheck(certification_id="CERT-P2", check_id="CHK-1", check_type="DOCUMENT", check_name="Docs", source_system="MYBLOCKS_RAG", status=CheckStatusEnum.ERROR.value),
    ]
    findings = [
        CertificationFinding(certification_id="CERT-P2", category="DOCUMENT", status=FindingStatusEnum.NOT_VERIFIED.value, severity="CRITICAL", title="Docs error", description="System error"),
    ]

    status = PolicyEngine.evaluate_certification(context, checks, findings)
    assert status == CertificationStatusEnum.ERROR


def test_remediation_endpoint_answers_five_questions(client, db_session):
    """GET /api/v1/certifications/{id}/remediation must answer:

    1. What requirement is not satisfied?
    2. Why is it not satisfied?
    3. What evidence is missing or failed?
    4. What exact action is required?
    5. Which external system must be checked again?
    """
    client.post("/api/v1/applications", json={
        "application_id": "APP-REM-1",
        "name": "Remediation Agent",
        "version": "1.0.0",
    })
    res = client.post("/api/v1/certifications", json={"application_id": "APP-REM-1"})
    cert_id = res.json()["certification_id"]

    from app.services.certification_service import CertificationService
    CertificationService().execute_certification_pipeline(db_session, cert_id)

    response = client.get(f"/api/v1/certifications/{cert_id}/remediation")
    assert response.status_code == 200
    report = response.json()
    assert report["certification_id"] == cert_id
    assert report["overall_status"] == "NOT_READY"
    assert report["actionable_items_count"] > 0

    for item in report["items"]:
        # Question 1: What requirement is not satisfied?
        assert item["requirement"] is not None
        # Question 2: Why is it not satisfied?
        assert len(item["reason"]) > 10
        # Question 3: What evidence is missing or failed?
        assert len(item["missing_or_failed_evidence"]) > 10
        # Question 4: What exact action is required?
        assert len(item["required_action"]) > 10
        # Question 5: Which external system must be checked again?
        assert item["target_system"] in ["MYBLOCKS_RAG", "MYBLOCKS_QA", "RULE_ENGINE", "ACE_VERSION_SERVICE", "ACE_SYSTEM", "AGENTGEN", "ACE"]
