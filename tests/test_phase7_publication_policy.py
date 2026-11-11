"""Phase 7 Deterministic Publication Policy Validation and Hardening Tests.

Validates:
1. Every mandatory condition passes -> READY_TO_PUBLISH
2. Each mandatory condition fails independently -> NOT_READY
3. Missing document requirement (e.g., 16/17 categories) -> NOT_READY
4. Missing rule result (e.g., 8/9 rules) -> NOT_READY
5. Unavailable QA (NOT_VERIFIED) -> NOT_READY
6. Version mismatch in QA or evidence -> NOT_READY
7. Missing or stale evidence -> NOT_READY
8. Evidence from another certification run -> NOT_READY
9. Unexpected internal error -> ERROR (never published)
10. Consistent publication status across REST and MCP endpoints
"""

import pytest
from datetime import datetime, timezone
from app.core.context import CertificationContext
from app.models.certification import CertificationStatusEnum
from app.models.certification_check import CertificationCheck, CheckStatusEnum, CheckTypeEnum
from app.models.finding import CertificationFinding, FindingStatusEnum, FindingCategoryEnum
from app.models.evidence import Evidence, SourceSystemEnum
from app.integrations.contracts import MANDATORY_17_DOC_CATEGORIES, MANDATORY_9_AGENT_RULES
from app.services.policy_engine import PolicyEngine
from app.services.certification_service import CertificationService
from app.services.application_service import ApplicationService
from app.schemas.application import ApplicationCreate
from app.schemas.certification import CertificationCreate
from app.mcp.server import ACEMCPServer


def _build_context(cert_id="CERT-P7-01", app_id="APP-P7", version="1.0.0"):
    return CertificationContext(cert_id, app_id, version)


def _build_passing_checks(cert_id="CERT-P7-01"):
    return [
        CertificationCheck(
            certification_id=cert_id,
            check_id="CHK-DOC-001",
            check_type=CheckTypeEnum.DOCUMENT.value,
            check_name="Docs",
            source_system="MYBLOCKS_RAG",
            status=CheckStatusEnum.PASS.value,
        ),
        CertificationCheck(
            certification_id=cert_id,
            check_id="CHK-QA-001",
            check_type=CheckTypeEnum.QA.value,
            check_name="QA",
            source_system="MYBLOCKS_QA",
            status=CheckStatusEnum.PASS.value,
        ),
        CertificationCheck(
            certification_id=cert_id,
            check_id="CHK-RULE-001",
            check_type=CheckTypeEnum.AGENT_RULES.value,
            check_name="Rules",
            source_system="RULE_ENGINE",
            status=CheckStatusEnum.PASS.value,
        ),
        CertificationCheck(
            certification_id=cert_id,
            check_id="CHK-VER-001",
            check_type=CheckTypeEnum.VERSION.value,
            check_name="Version",
            source_system="ACE",
            status=CheckStatusEnum.PASS.value,
        ),
    ]


def _build_passing_findings(cert_id="CERT-P7-01"):
    findings = []
    # 17 document category findings
    for cat in MANDATORY_17_DOC_CATEGORIES:
        findings.append(
            CertificationFinding(
                certification_id=cert_id,
                check_id="CHK-DOC-001",
                requirement_id=f"DOC-{cat.replace('_', '-')}",
                finding_code=f"FINDING-DOC-{cat}",
                category=FindingCategoryEnum.DOCUMENT.value,
                status=FindingStatusEnum.PASS.value,
                title=f"Doc {cat}",
                description="Verified",
            )
        )
    # QA finding
    findings.append(
        CertificationFinding(
            certification_id=cert_id,
            check_id="CHK-QA-001",
            requirement_id="QA-TEST-SUITE",
            finding_code="FINDING-QA-001",
            category=FindingCategoryEnum.QA.value,
            status=FindingStatusEnum.PASS.value,
            title="QA Tests",
            description="All tests passed",
        )
    )
    # 9 agent rule findings
    for r in MANDATORY_9_AGENT_RULES:
        findings.append(
            CertificationFinding(
                certification_id=cert_id,
                check_id="CHK-RULE-001",
                requirement_id=r["rule_id"],
                finding_code=f"FINDING-{r['rule_id']}",
                category=FindingCategoryEnum.RULE.value,
                status=FindingStatusEnum.PASS.value,
                title=r["name"],
                description="Rule satisfied",
            )
        )
    # Version consistency finding
    findings.append(
        CertificationFinding(
            certification_id=cert_id,
            check_id="CHK-VER-001",
            requirement_id="VERSION-CONSISTENCY",
            finding_code="FINDING-VER-001",
            category=FindingCategoryEnum.SYSTEM.value,
            status=FindingStatusEnum.PASS.value,
            title="Version Consistency",
            description="Consistent",
        )
    )
    return findings


def _build_passing_evidence(cert_id="CERT-P7-01", app_id="APP-P7", version="1.0.0"):
    return [
        Evidence(
            certification_id=cert_id,
            source_system="MYBLOCKS_RAG",
            evidence_type="DOCUMENT_CATEGORY_VERIFICATION",
            evidence_data={"verified_count": 17, "version": version},
            source_version=version,
        ),
        Evidence(
            certification_id=cert_id,
            source_system="MYBLOCKS_QA",
            evidence_type="QA_TEST_RUN_REPORT",
            evidence_data={"application_id": app_id, "version": version, "passed": True, "status": "PASS"},
            source_version=version,
        ),
        Evidence(
            certification_id=cert_id,
            source_system="RULE_ENGINE",
            evidence_type="RULE_EVALUATION_REPORT",
            evidence_data={"total_rules": 9, "passed_rules": 9, "passed": True, "version": version},
            source_version=version,
        ),
        Evidence(
            certification_id=cert_id,
            source_system="ACE",
            evidence_type="VERSION_CONSISTENCY_AUDIT",
            evidence_data={"is_consistent": True, "version": version},
            source_version=version,
        ),
    ]


def test_phase7_every_mandatory_condition_passes():
    """1. All 17 docs, 9 rules, QA, version consistency, valid evidence -> READY_TO_PUBLISH."""
    context = _build_context()
    checks = _build_passing_checks()
    findings = _build_passing_findings()
    evidence = _build_passing_evidence()

    result = PolicyEngine.evaluate_certification(context, checks, findings, evidence)
    assert result == CertificationStatusEnum.READY_TO_PUBLISH


@pytest.mark.parametrize(
    "failed_check_id",
    ["CHK-DOC-001", "CHK-QA-001", "CHK-RULE-001", "CHK-VER-001"],
)
def test_phase7_each_mandatory_condition_fails_independently(failed_check_id):
    """2. Each mandatory condition fails independently -> NOT_READY."""
    context = _build_context()
    checks = _build_passing_checks()
    findings = _build_passing_findings()
    evidence = _build_passing_evidence()

    for chk in checks:
        if chk.check_id == failed_check_id:
            chk.status = CheckStatusEnum.FAIL.value

    result = PolicyEngine.evaluate_certification(context, checks, findings, evidence)
    assert result == CertificationStatusEnum.NOT_READY
    assert result not in [CertificationStatusEnum.READY_TO_PUBLISH, "BLOCKED", "REJECTED"]


def test_phase7_missing_document_requirement():
    """3. Missing document requirement: only 16 of 17 categories verified -> NOT_READY."""
    context = _build_context()
    checks = _build_passing_checks()
    evidence = _build_passing_evidence()

    # Exclude "OTHER" from document findings
    findings = [
        f for f in _build_passing_findings()
        if f.requirement_id != "DOC-OTHER"
    ]

    result = PolicyEngine.evaluate_certification(context, checks, findings, evidence)
    assert result == CertificationStatusEnum.NOT_READY


def test_phase7_missing_rule_result():
    """4. Missing rule result: only 8 of 9 rules evaluated -> NOT_READY."""
    context = _build_context()
    checks = _build_passing_checks()
    evidence = _build_passing_evidence()

    # Exclude "RULE-9" from findings
    findings = [
        f for f in _build_passing_findings()
        if f.requirement_id != "RULE-9"
    ]

    result = PolicyEngine.evaluate_certification(context, checks, findings, evidence)
    assert result == CertificationStatusEnum.NOT_READY


def test_phase7_unavailable_qa():
    """5. Unavailable QA (NOT_VERIFIED status) -> NOT_READY (never PASS)."""
    context = _build_context()
    checks = _build_passing_checks()
    findings = _build_passing_findings()
    evidence = _build_passing_evidence()

    for chk in checks:
        if chk.check_id == "CHK-QA-001":
            chk.status = CheckStatusEnum.NOT_VERIFIED.value

    result = PolicyEngine.evaluate_certification(context, checks, findings, evidence)
    assert result == CertificationStatusEnum.NOT_READY


def test_phase7_version_mismatch():
    """6. Version mismatch in QA evidence (e.g. 1.0.1 != 1.0.0) -> NOT_READY."""
    context = _build_context(version="1.0.0")
    checks = _build_passing_checks()
    findings = _build_passing_findings()
    # Evidence has different version
    evidence = _build_passing_evidence(version="1.0.1")

    result = PolicyEngine.evaluate_certification(context, checks, findings, evidence)
    assert result == CertificationStatusEnum.NOT_READY


def test_phase7_missing_or_stale_evidence():
    """7. Missing evidence list or stale evidence flag -> NOT_READY."""
    context = _build_context()
    checks = _build_passing_checks()
    findings = _build_passing_findings()

    # 7A: Empty evidence
    res_empty = PolicyEngine.evaluate_certification(context, checks, findings, evidence=[])
    assert res_empty == CertificationStatusEnum.NOT_READY

    # 7B: Stale evidence
    stale_evidence = _build_passing_evidence()
    stale_evidence[1].evidence_data["is_stale"] = True
    res_stale = PolicyEngine.evaluate_certification(context, checks, findings, evidence=stale_evidence)
    assert res_stale == CertificationStatusEnum.NOT_READY


def test_phase7_evidence_from_another_certification_run():
    """8. Evidence from another certification run -> NOT_READY."""
    context = _build_context(cert_id="CERT-CURRENT")
    checks = _build_passing_checks(cert_id="CERT-CURRENT")
    findings = _build_passing_findings(cert_id="CERT-CURRENT")
    # Evidence belongs to an older certification
    evidence = _build_passing_evidence(cert_id="CERT-OLD-RUN-001")

    result = PolicyEngine.evaluate_certification(context, checks, findings, evidence)
    assert result == CertificationStatusEnum.NOT_READY


def test_phase7_unexpected_internal_error(monkeypatch):
    """9. Internal unexpected error must return ERROR and never permit publication."""
    context = _build_context()
    checks = _build_passing_checks()
    findings = _build_passing_findings()
    evidence = _build_passing_evidence()

    # 9A: Check has status ERROR
    checks[0].status = CheckStatusEnum.ERROR.value
    res_err = PolicyEngine.evaluate_certification(context, checks, findings, evidence)
    assert res_err == CertificationStatusEnum.ERROR

    # 9B: Unexpected exception inside policy engine returns safe ERROR status
    def _raise(*args, **kwargs):
        raise RuntimeError("Unexpected internal crash")

    monkeypatch.setattr(PolicyEngine, "_evaluate_internal", _raise)
    res_crash = PolicyEngine.evaluate_certification(context, checks, findings, evidence)
    assert res_crash == CertificationStatusEnum.ERROR


def test_phase7_consistent_publication_status_across_endpoints(client, db_session):
    """10. Publication status is consistent across REST and MCP endpoints (no contradictions)."""
    app_id = "APP-P7-CONSIST"
    version = "1.0.0"

    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id=app_id, name="Consistent App", version=version),
    )

    # 1. Before certification: both REST and MCP report NOT_READY
    rest_res = client.get(f"/api/v1/applications/{app_id}/publication-status")
    assert rest_res.status_code == 200
    rest_data = rest_res.json()
    assert rest_data["publication_status"] == "NOT_READY"
    assert rest_data["is_ready_to_publish"] is False

    mcp_data = ACEMCPServer._tool_get_publication_status(
        {"application_id": app_id, "version": version}, db_session
    )
    assert mcp_data["publication_status"] == "NOT_READY"
    assert mcp_data["is_ready_to_publish"] is False

    # Exact parity between REST and MCP
    assert rest_data["publication_status"] == mcp_data["publication_status"]
    assert rest_data["is_ready_to_publish"] == mcp_data["is_ready_to_publish"]
    assert rest_data["publication_status"] not in ["BLOCKED", "REJECTED"]
