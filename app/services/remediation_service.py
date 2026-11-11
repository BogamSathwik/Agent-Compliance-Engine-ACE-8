from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.finding import CertificationFinding, FindingStatusEnum, RemediationStatusEnum
from app.schemas.remediation import RemediationItem, RemediationReport
from app.services.evidence_service import EvidenceService
from app.core.exceptions import ACEException
from app.core.logging import get_logger

logger = get_logger("ace.remediation_service")


class RemediationService:
    """Generates precise, actionable remediation guidance and manages remediation lifecycle."""

    TARGET_SYSTEM_MAP = {
        "DOCUMENT": "MYBLOCKS_RAG",
        "QA": "MYBLOCKS_QA",
        "RULE": "RULE_ENGINE",
        "VERSION": "ACE_VERSION_SERVICE",
        "SYSTEM": "ACE_SYSTEM",
        "INTEGRATION": "AGENTGEN",
    }

    @classmethod
    def generate_remediation_report(
        cls,
        certification_id: str,
        application_id: str,
        application_version: str,
        overall_status: str,
        findings: List[CertificationFinding],
    ) -> RemediationReport:
        """Create structured remediation report for all non-passing findings."""
        items: List[RemediationItem] = []

        for f in findings:
            if f.status != FindingStatusEnum.PASS.value:
                target_sys = cls.TARGET_SYSTEM_MAP.get(f.category, "ACE")

                reason = f.description or f"Requirement '{f.requirement_id or f.category}' status is {f.status}."
                missing_evidence = f"Evidence from {target_sys} for requirement {f.requirement_id or f.category} is missing or non-compliant."
                action = f.remediation or f"Review {f.category} specifications and trigger re-verification in {target_sys}."

                item = RemediationItem(
                    finding_id=f.id,
                    requirement=f.requirement_id or f.category,
                    finding_code=f.finding_code or f"FINDING-{f.category}-{f.id}",
                    check_id=f.check_id,
                    status=f.status,
                    remediation_status=getattr(f, "remediation_status", RemediationStatusEnum.OPEN.value) or RemediationStatusEnum.OPEN.value,
                    severity=f.severity,
                    reason=reason,
                    missing_or_failed_evidence=missing_evidence,
                    required_action=action,
                    target_system=target_sys,
                )
                items.append(item)

        report = RemediationReport(
            certification_id=certification_id,
            application_id=application_id,
            application_version=application_version,
            overall_status=overall_status,
            actionable_items_count=len(items),
            items=items,
        )

        logger.info(
            f"Remediation generated for {certification_id}: {len(items)} actionable items",
            extra={
                "event": "remediation_generated",
                "certification_id": certification_id,
                "actionable_count": len(items),
            },
        )
        return report

    @classmethod
    def update_remediation_status(
        cls,
        db: Session,
        certification_id: str,
        status: str,
        finding_id: Optional[int] = None,
        finding_code: Optional[str] = None,
        notes: Optional[str] = None,
        actor: str = "operator",
    ) -> CertificationFinding:
        """Update remediation lifecycle state for a finding (OPEN -> IN_PROGRESS -> RESOLVED).

        Note: Setting remediation_status to RESOLVED tracks remediation progress but does NOT
        override verification or grant READY_TO_PUBLISH. Re-certification is required.
        """
        valid_statuses = [e.value for e in RemediationStatusEnum]
        clean_status = status.upper().strip()
        if clean_status not in valid_statuses:
            raise ACEException(
                f"Invalid remediation status '{status}'. Must be one of: {valid_statuses}",
                code="INVALID_STATUS",
                status_code=400,
            )

        query = db.query(CertificationFinding).filter(
            CertificationFinding.certification_id == certification_id
        )
        if finding_id is not None:
            query = query.filter(CertificationFinding.id == finding_id)
        elif finding_code is not None:
            query = query.filter(CertificationFinding.finding_code == finding_code)
        else:
            raise ACEException(
                "Either finding_id or finding_code must be provided",
                code="INVALID_ARGUMENT",
                status_code=400,
            )

        finding = query.first()
        if not finding:
            raise ACEException(
                f"Finding not found for certification {certification_id}",
                code="FINDING_NOT_FOUND",
                status_code=404,
            )

        old_status = getattr(finding, "remediation_status", RemediationStatusEnum.OPEN.value)
        finding.remediation_status = clean_status
        db.commit()
        db.refresh(finding)

        EvidenceService.record_audit_event(
            db=db,
            event_type="REMEDIATION_STATUS_UPDATED",
            actor=actor,
            event_data={
                "certification_id": certification_id,
                "finding_id": finding.id,
                "finding_code": finding.finding_code,
                "requirement_id": finding.requirement_id,
                "old_remediation_status": old_status,
                "new_remediation_status": finding.remediation_status,
                "notes": notes,
            },
            certification_id=certification_id,
        )

        logger.info(
            f"Remediation status updated for {finding.finding_code or finding.id}: {old_status} -> {finding.remediation_status}",
            extra={
                "event": "remediation_status_updated",
                "certification_id": certification_id,
                "finding_id": finding.id,
                "remediation_status": finding.remediation_status,
            },
        )
        return finding
