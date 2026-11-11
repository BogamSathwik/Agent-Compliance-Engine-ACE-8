"""Evidence, Audit logging, and Integration run tracking service."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.evidence import Evidence, SourceSystemEnum
from app.models.audit_event import AuditEvent
from app.models.integration_run import IntegrationRun
from app.core.security import generate_secure_id
from app.core.logging import get_logger

logger = get_logger("ace.evidence_service")


def _sanitize_data(data: Any) -> Any:
    """Recursively scrub sensitive credential keys from evidence dictionaries."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(secret_term in k_lower for secret_term in ("token", "secret", "password", "api_key", "authorization")):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = _sanitize_data(v)
        return sanitized
    elif isinstance(data, list):
        return [_sanitize_data(item) for item in data]
    return data


class EvidenceService:
    """Handles structured evidence collection, integration run tracking, and immutable audit trail."""

    @staticmethod
    def record_evidence(
        db: Session,
        certification_id: str,
        source_system: SourceSystemEnum,
        evidence_type: str,
        evidence_data: Dict[str, Any],
        finding_id: Optional[int] = None,
        check_id: Optional[str] = None,
        source_reference: Optional[str] = None,
        source_version: Optional[str] = None,
        source_run_id: Optional[str] = None,
        source_timestamp: Optional[datetime] = None,
        hash: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> Evidence:
        """Persist structured evidence entry with complete provenance and idempotency."""
        clean_data = _sanitize_data(evidence_data)
        src_val = (
            source_system.value
            if isinstance(source_system, SourceSystemEnum)
            else str(source_system)
        )

        query = db.query(Evidence).filter(
            Evidence.certification_id == certification_id,
            Evidence.source_system == src_val,
            Evidence.evidence_type == evidence_type,
        )
        if source_reference:
            query = query.filter(Evidence.source_reference == source_reference)
        elif check_id is not None:
            query = query.filter(Evidence.check_id == check_id)

        existing = query.first()
        if existing:
            existing.evidence_data = clean_data
            if check_id is not None:
                existing.check_id = check_id
            if finding_id is not None:
                existing.finding_id = finding_id
            existing.source_reference = source_reference
            existing.source_version = source_version
            existing.source_run_id = source_run_id
            existing.source_timestamp = source_timestamp
            existing.hash = hash
            existing.confidence = confidence
            db.commit()
            db.refresh(existing)
            logger.info(
                f"Evidence updated for {certification_id}: [{src_val}] {evidence_type}",
                extra={
                    "event": "evidence_updated",
                    "certification_id": certification_id,
                    "check_id": check_id,
                    "source_system": src_val,
                    "evidence_type": evidence_type,
                },
            )
            return existing

        evidence = Evidence(
            certification_id=certification_id,
            check_id=check_id,
            finding_id=finding_id,
            source_system=src_val,
            source_reference=source_reference,
            evidence_type=evidence_type,
            evidence_data=clean_data,
            source_version=source_version,
            source_run_id=source_run_id,
            source_timestamp=source_timestamp,
            hash=hash,
            confidence=confidence,
        )
        db.add(evidence)
        db.commit()
        db.refresh(evidence)

        logger.info(
            f"Evidence collected for {certification_id}: [{evidence.source_system}] {evidence_type}",
            extra={
                "event": "evidence_collected",
                "certification_id": certification_id,
                "check_id": check_id,
                "source_system": evidence.source_system,
                "evidence_type": evidence_type,
            },
        )
        return evidence

    @staticmethod
    def get_evidence_for_certification(
        db: Session, certification_id: str
    ) -> List[Evidence]:
        """Fetch all evidence linked to a certification run."""
        return (
            db.query(Evidence)
            .filter(Evidence.certification_id == certification_id)
            .order_by(Evidence.collected_at.asc())
            .all()
        )

    @staticmethod
    def record_integration_run(
        db: Session,
        certification_id: str,
        source_system: str,
        operation: str,
        status: str,
        external_application_id: Optional[str] = None,
        external_version: Optional[str] = None,
        external_run_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        response_metadata: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> IntegrationRun:
        """Record external verification run correlation record with idempotency."""
        clean_metadata = _sanitize_data(response_metadata) if response_metadata else None

        # Check for existing integration run record to prevent duplicate entries
        existing = (
            db.query(IntegrationRun)
            .filter(
                IntegrationRun.certification_id == certification_id,
                IntegrationRun.source_system == source_system,
                IntegrationRun.operation == operation,
            )
            .first()
        )
        if existing:
            existing.status = status
            existing.external_application_id = external_application_id
            existing.external_version = external_version
            existing.external_run_id = external_run_id
            existing.started_at = started_at
            existing.completed_at = completed_at
            existing.response_metadata = clean_metadata
            existing.error_code = error_code
            existing.error_message = error_message
            db.commit()
            db.refresh(existing)
            return existing

        run_id = generate_secure_id("INT", 10)
        integration_run = IntegrationRun(
            certification_id=certification_id,
            integration_run_id=run_id,
            source_system=source_system,
            operation=operation,
            status=status,
            external_application_id=external_application_id,
            external_version=external_version,
            external_run_id=external_run_id,
            started_at=started_at,
            completed_at=completed_at,
            response_metadata=clean_metadata,
            error_code=error_code,
            error_message=error_message,
        )
        db.add(integration_run)
        db.commit()
        db.refresh(integration_run)
        return integration_run

    @staticmethod
    def get_integration_runs(
        db: Session, certification_id: str
    ) -> List[IntegrationRun]:
        """Fetch all external integration runs correlated with this certification."""
        return (
            db.query(IntegrationRun)
            .filter(IntegrationRun.certification_id == certification_id)
            .order_by(IntegrationRun.created_at.asc())
            .all()
        )

    @staticmethod
    def record_audit_event(
        db: Session,
        event_type: str,
        actor: str,
        event_data: Dict[str, Any],
        certification_id: Optional[str] = None,
    ) -> AuditEvent:
        """Persist an immutable audit log entry."""
        event = AuditEvent(
            certification_id=certification_id,
            event_type=event_type,
            actor=actor,
            event_data=event_data,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        logger.info(
            f"Audit event recorded: {event_type}",
            extra={
                "event": event_type,
                "certification_id": certification_id,
                "actor": actor,
                "extra_data": event_data,
            },
        )
        return event

    @staticmethod
    def get_audit_trail(
        db: Session, certification_id: str
    ) -> List[AuditEvent]:
        """Fetch full audit trail for a certification run."""
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.certification_id == certification_id)
            .order_by(AuditEvent.created_at.asc())
            .all()
        )
