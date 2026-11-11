"""Tests for VersionConsistencyService."""

from app.core.context import CertificationContext
from app.services.version_consistency_service import VersionConsistencyService
from app.models.finding import FindingStatusEnum


def test_version_consistency_matching_pass():
    """Consistent identities across RAG, QA, and Rule Engine resolve to PASS."""
    context = CertificationContext(
        certification_id="CERT-TEST-001",
        application_id="APP-1001",
        application_version="1.4.2",
        commit_hash="8fa91bc",
    )

    reports = [
        {"source_system": "MYBLOCKS_RAG", "application_id": "APP-1001", "version": "1.4.2", "commit_hash": "8fa91bc"},
        {"source_system": "MYBLOCKS_QA", "application_id": "APP-1001", "version": "1.4.2", "commit_hash": "8fa91bc"},
        {"source_system": "RULE_ENGINE", "application_id": "APP-1001", "version": "1.4.2", "commit_hash": "8fa91bc"},
    ]

    report = VersionConsistencyService.verify_consistency(context, reports)
    assert report.is_consistent is True
    assert report.status == FindingStatusEnum.PASS
    assert len(report.discrepancies) == 0


def test_version_consistency_mismatch_not_verified():
    """Mismatched version in one subsystem resolves to NOT_VERIFIED with explicit discrepancy."""
    context = CertificationContext(
        certification_id="CERT-TEST-002",
        application_id="APP-1001",
        application_version="1.4.2",
    )

    reports = [
        {"source_system": "MYBLOCKS_RAG", "application_id": "APP-1001", "version": "1.4.2"},
        {"source_system": "MYBLOCKS_QA", "application_id": "APP-1001", "version": "1.4.1"},  # Mismatched version
        {"source_system": "RULE_ENGINE", "application_id": "APP-1001", "version": "1.4.2"},
    ]

    report = VersionConsistencyService.verify_consistency(context, reports)
    assert report.is_consistent is False
    assert report.status == FindingStatusEnum.NOT_VERIFIED
    assert len(report.discrepancies) == 1
    assert "MYBLOCKS_QA" in report.discrepancies[0]
    assert "1.4.1" in report.discrepancies[0]
    assert report.remediation is not None


def test_application_id_mismatch_not_verified():
    """Mismatched application ID resolves to NOT_VERIFIED."""
    context = CertificationContext(
        certification_id="CERT-TEST-003",
        application_id="APP-1001",
        application_version="1.4.2",
    )

    reports = [
        {"source_system": "RULE_ENGINE", "application_id": "APP-9999", "version": "1.4.2"},
    ]

    report = VersionConsistencyService.verify_consistency(context, reports)
    assert report.is_consistent is False
    assert report.status == FindingStatusEnum.NOT_VERIFIED
    assert any("APP-9999" in d for d in report.discrepancies)
