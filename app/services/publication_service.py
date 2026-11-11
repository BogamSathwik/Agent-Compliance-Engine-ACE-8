"""Publication Service managing the publication lifecycle to AgentGen Pro.

Enforces strict re-validation of PolicyEngine certification before publication,
tracks the lifecycle CERTIFIED -> PUBLICATION_REQUESTED -> PUBLISHED,
and guarantees idempotency and safety.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ApplicationNotFoundError,
    CertificationNotFoundError,
    PublicationAlreadyExistsError,
    PublicationEligibilityError,
    PublicationNotFoundError,
)
from app.core.logging import get_logger
from app.core.security import generate_secure_id
from app.integrations.publication_client import (
    AgentGenPublicationClient,
    ExternalPublicationResult,
    PublicationClientProtocol,
)
from app.models.application import Application
from app.models.certification import CertificationRun, CertificationStatusEnum
from app.models.certification_check import CertificationCheck
from app.models.finding import CertificationFinding
from app.models.publication import PublicationRecord, PublicationStatusEnum
from app.core.context import CertificationContext
from app.services.application_service import ApplicationService
from app.services.evidence_service import EvidenceService
from app.services.policy_engine import PolicyEngine

logger = get_logger("ace.publication_service")


class PublicationService:
    """Service orchestrating publication to AgentGen Pro."""

    def __init__(self, publication_client: Optional[PublicationClientProtocol] = None):
        self.publication_client = publication_client or AgentGenPublicationClient()

    def check_eligibility(
        self,
        db: Session,
        application_id: str,
        version: Optional[str] = None,
    ) -> Tuple[Optional[CertificationRun], bool, str]:
        """Strictly revalidate that application version passes all publication conditions.

        Revalidates:
        1. Certification run exists and is READY_TO_PUBLISH.
        2. Exact version match (no cross-version publication).
        3. PolicyEngine deterministically evaluates to READY_TO_PUBLISH on current checks/evidence.
        4. All 17 document categories are verified.
        5. All 9 mandatory agent rules pass.
        6. Authoritative QA passes for exact version.
        7. Version consistency passes.
        8. Evidence is valid, fresh, and not stale.
        """
        app = ApplicationService.get_application(db, application_id)
        target_version = version or app.current_version

        latest_run = (
            db.query(CertificationRun)
            .filter(
                CertificationRun.application_id == app.application_id,
                CertificationRun.application_version == target_version,
            )
            .order_by(CertificationRun.created_at.desc(), CertificationRun.id.desc())
            .first()
        )

        if not latest_run:
            return None, False, f"No certification run exists for application '{application_id}' at version '{target_version}'"

        if latest_run.status != CertificationStatusEnum.READY_TO_PUBLISH.value:
            return latest_run, False, f"Latest certification run {latest_run.certification_id} is in status '{latest_run.status}', not 'READY_TO_PUBLISH'"

        if latest_run.application_version != target_version:
            return latest_run, False, f"Version mismatch: run certified for '{latest_run.application_version}', but requested for '{target_version}'"

        # Load checks, findings, and evidence
        checks = (
            db.query(CertificationCheck)
            .filter(CertificationCheck.certification_id == latest_run.certification_id)
            .all()
        )
        findings = (
            db.query(CertificationFinding)
            .filter(CertificationFinding.certification_id == latest_run.certification_id)
            .all()
        )
        evidence = EvidenceService.get_evidence_for_certification(db, latest_run.certification_id)

        context = CertificationContext(
            certification_id=latest_run.certification_id,
            application_id=latest_run.application_id,
            application_version=latest_run.application_version,
            commit_hash=latest_run.commit_hash,
            submission_id=latest_run.submission_id,
            trigger_type=latest_run.trigger_type,
            policy_version=latest_run.policy_version,
            application_version_id=latest_run.application_version_id,
        )

        # Re-evaluate through authoritative PolicyEngine
        revalidated_status = PolicyEngine.evaluate_certification(
            context=context,
            checks=checks,
            findings=findings,
            evidence=evidence,
        )

        if revalidated_status != CertificationStatusEnum.READY_TO_PUBLISH:
            return latest_run, False, f"Deterministic PolicyEngine re-evaluation resulted in '{revalidated_status.value}', not 'READY_TO_PUBLISH'"

        return latest_run, True, "Eligible for publication"

    def request_publication(
        self,
        db: Session,
        application_id: str,
        version: Optional[str] = None,
        notes: Optional[str] = None,
        actor: str = "operator",
    ) -> PublicationRecord:
        """Execute safe publication request workflow: CERTIFIED -> PUBLICATION_REQUESTED -> PUBLISHED."""
        app = ApplicationService.get_application(db, application_id)
        target_version = version or app.current_version

        # 1. Revalidate eligibility immediately before publication
        latest_run, is_eligible, reason = self.check_eligibility(db, app.application_id, target_version)
        if not is_eligible or not latest_run:
            logger.warning(
                f"Publication denied for {app.application_id} (v{target_version}): {reason}",
                extra={
                    "event": "publication_eligibility_denied",
                    "application_id": app.application_id,
                    "version": target_version,
                    "reason": reason,
                },
            )
            raise PublicationEligibilityError(app.application_id, target_version, reason)

        # 2. Idempotency Check: Existing publications for this exact application and version
        existing_pub = (
            db.query(PublicationRecord)
            .filter(
                PublicationRecord.application_id == app.application_id,
                PublicationRecord.application_version == target_version,
            )
            .order_by(PublicationRecord.created_at.desc(), PublicationRecord.id.desc())
            .first()
        )

        if existing_pub:
            # If already confirmed PUBLISHED, do not republish (idempotent)
            if existing_pub.status == PublicationStatusEnum.PUBLISHED.value:
                logger.info(
                    f"Application {app.application_id} (v{target_version}) is already published ({existing_pub.publication_id})",
                    extra={"event": "publication_idempotent_match", "publication_id": existing_pub.publication_id},
                )
                return existing_pub

            # If request is currently in-flight, return the active record
            if existing_pub.status == PublicationStatusEnum.PUBLICATION_REQUESTED.value:
                logger.info(
                    f"Publication request for {app.application_id} (v{target_version}) is already in-flight ({existing_pub.publication_id})",
                    extra={"event": "publication_request_in_flight", "publication_id": existing_pub.publication_id},
                )
                return existing_pub

        # 3. Create distinct PublicationRecord in CERTIFIED state
        pub_id = generate_secure_id("PUB", 12)
        retry_num = (existing_pub.retry_count + 1) if existing_pub and existing_pub.status in (
            PublicationStatusEnum.PUBLICATION_FAILED.value,
            PublicationStatusEnum.PUBLICATION_STATUS_UNKNOWN.value,
        ) else 0

        pub_record = PublicationRecord(
            publication_id=pub_id,
            application_id=app.application_id,
            application_version=target_version,
            application_version_id=latest_run.application_version_id,
            certification_id=latest_run.certification_id,
            submission_id=latest_run.submission_id,
            status=PublicationStatusEnum.PUBLICATION_REQUESTED.value,
            requested_by=actor,
            retry_count=retry_num,
        )
        db.add(pub_record)
        db.commit()
        db.refresh(pub_record)

        EvidenceService.record_audit_event(
            db=db,
            event_type="PUBLICATION_REQUESTED",
            actor=actor,
            event_data={
                "publication_id": pub_record.publication_id,
                "application_id": pub_record.application_id,
                "version": pub_record.application_version,
                "certification_id": pub_record.certification_id,
                "submission_id": pub_record.submission_id,
                "retry_count": pub_record.retry_count,
            },
            certification_id=pub_record.certification_id,
        )

        # 4. Dispatch request to AgentGen Pro via client (MCP or REST)
        result: ExternalPublicationResult = self.publication_client.request_publication(
            application_id=pub_record.application_id,
            version=pub_record.application_version,
            certification_id=pub_record.certification_id,
            submission_id=pub_record.submission_id,
            notes=notes,
        )

        EvidenceService.record_integration_run(
            db=db,
            certification_id=pub_record.certification_id,
            source_system="AGENTGEN",
            operation="publish_application",
            status=result.status,
            external_application_id=pub_record.application_id,
            external_version=pub_record.application_version,
            external_run_id=result.external_publication_id or pub_record.publication_id,
            response_metadata=result.raw_response or result.confirmation_details or {"status": result.status},
            error_code=result.error_code,
            error_message=result.error_message,
        )

        # 5. Process External Result
        if result.is_timeout or result.is_ambiguous or result.status == "UNKNOWN":
            pub_record.status = PublicationStatusEnum.PUBLICATION_STATUS_UNKNOWN.value
            pub_record.error_code = result.error_code or "TIMEOUT"
            pub_record.error_message = result.error_message or "External publication request timed out or was ambiguous"
            EvidenceService.record_audit_event(
                db=db,
                event_type="PUBLICATION_STATUS_UNKNOWN",
                actor="agentgen_client",
                event_data={"publication_id": pub_record.publication_id, "error": pub_record.error_message},
                certification_id=pub_record.certification_id,
            )
        elif result.status == "PUBLISHED":
            # Authoritative confirmation received immediately
            pub_record.status = PublicationStatusEnum.PUBLISHED.value
            pub_record.external_publication_id = result.external_publication_id
            pub_record.external_status = "PUBLISHED"
            pub_record.external_confirmation = result.confirmation_details
            pub_record.confirmed_at = datetime.now(timezone.utc)
            EvidenceService.record_audit_event(
                db=db,
                event_type="PUBLICATION_CONFIRMED",
                actor="agentgen_client",
                event_data={
                    "publication_id": pub_record.publication_id,
                    "external_publication_id": result.external_publication_id,
                },
                certification_id=pub_record.certification_id,
            )
        elif result.status in ("FAILED", "CONFIG_MISSING") or result.error_code:
            pub_record.status = PublicationStatusEnum.PUBLICATION_FAILED.value
            pub_record.error_code = result.error_code or "PUBLICATION_FAILED"
            pub_record.error_message = result.error_message or "AgentGen Pro rejected publication"
            EvidenceService.record_audit_event(
                db=db,
                event_type="PUBLICATION_FAILED",
                actor="agentgen_client",
                event_data={
                    "publication_id": pub_record.publication_id,
                    "error_code": pub_record.error_code,
                    "error_message": pub_record.error_message,
                },
                certification_id=pub_record.certification_id,
            )
        else:
            # Staged / in-flight awaiting external webhook confirmation
            pub_record.status = PublicationStatusEnum.PUBLICATION_REQUESTED.value
            pub_record.external_publication_id = result.external_publication_id
            pub_record.external_confirmation = result.confirmation_details

        db.commit()
        db.refresh(pub_record)
        return pub_record

    def get_publication_status(
        self,
        db: Session,
        application_id: str,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve unified publication status and policy eligibility."""
        app = ApplicationService.get_application(db, application_id)
        target_version = version or app.current_version

        latest_run, is_eligible, reason = self.check_eligibility(db, app.application_id, target_version)

        latest_pub = (
            db.query(PublicationRecord)
            .filter(
                PublicationRecord.application_id == app.application_id,
                PublicationRecord.application_version == target_version,
            )
            .order_by(PublicationRecord.created_at.desc(), PublicationRecord.id.desc())
            .first()
        )

        pub_status = latest_pub.status if latest_pub else "NOT_REQUESTED"
        is_published = latest_pub.status == PublicationStatusEnum.PUBLISHED.value if latest_pub else False

        return {
            "application_id": app.application_id,
            "application_name": app.name,
            "version": target_version,
            "is_eligible_for_publication": is_eligible,
            "eligibility_reason": reason,
            "certification_status": latest_run.status if latest_run else "NOT_CERTIFIED",
            "latest_certification_id": latest_run.certification_id if latest_run else None,
            "publication_status": pub_status,
            "is_published": is_published,
            "latest_publication_id": latest_pub.publication_id if latest_pub else None,
            "external_publication_id": latest_pub.external_publication_id if latest_pub else None,
            "last_evaluated_at": latest_run.completed_at.isoformat() if latest_run and latest_run.completed_at else None,
            "last_published_at": latest_pub.confirmed_at.isoformat() if latest_pub and latest_pub.confirmed_at else None,
        }

    def get_failure_details(
        self,
        db: Session,
        application_id: str,
        version: Optional[str] = None,
        publication_id: Optional[str] = None,
    ) -> Optional[PublicationRecord]:
        """Fetch the latest failed or unknown publication record."""
        app = ApplicationService.get_application(db, application_id)
        target_version = version or app.current_version

        query = db.query(PublicationRecord).filter(
            PublicationRecord.application_id == app.application_id,
            PublicationRecord.application_version == target_version,
        )
        if publication_id:
            query = query.filter(PublicationRecord.publication_id == publication_id)

        failed_record = (
            query.filter(
                PublicationRecord.status.in_([
                    PublicationStatusEnum.PUBLICATION_FAILED.value,
                    PublicationStatusEnum.PUBLICATION_STATUS_UNKNOWN.value,
                ])
            )
            .order_by(PublicationRecord.created_at.desc(), PublicationRecord.id.desc())
            .first()
        )
        return failed_record

    def confirm_external_publication(
        self,
        db: Session,
        publication_id: str,
        external_publication_id: str,
        status: str,
        confirmation_details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        actor: str = "agentgen_webhook",
    ) -> PublicationRecord:
        """Authoritatively update publication record upon external confirmation from AgentGen Pro."""
        pub_record = (
            db.query(PublicationRecord)
            .filter(PublicationRecord.publication_id == publication_id)
            .first()
        )
        if not pub_record:
            # Fallback search by external_publication_id
            pub_record = (
                db.query(PublicationRecord)
                .filter(PublicationRecord.external_publication_id == external_publication_id)
                .first()
            )
        if not pub_record:
            raise PublicationNotFoundError(publication_id or external_publication_id)

        status_norm = status.upper()
        if status_norm == "PUBLISHED":
            pub_record.status = PublicationStatusEnum.PUBLISHED.value
            pub_record.external_publication_id = external_publication_id
            pub_record.external_status = "PUBLISHED"
            pub_record.external_confirmation = confirmation_details or {}
            pub_record.confirmed_at = datetime.now(timezone.utc)
            EvidenceService.record_audit_event(
                db=db,
                event_type="PUBLICATION_CONFIRMED",
                actor=actor,
                event_data={
                    "publication_id": pub_record.publication_id,
                    "external_publication_id": external_publication_id,
                },
                certification_id=pub_record.certification_id,
            )
        elif status_norm in ("FAILED", "REJECTED"):
            pub_record.status = PublicationStatusEnum.PUBLICATION_FAILED.value
            pub_record.error_code = "EXTERNAL_REJECTION"
            pub_record.error_message = error_message or "AgentGen Pro confirmed publication rejection"
            EvidenceService.record_audit_event(
                db=db,
                event_type="PUBLICATION_FAILED",
                actor=actor,
                event_data={
                    "publication_id": pub_record.publication_id,
                    "error_message": pub_record.error_message,
                },
                certification_id=pub_record.certification_id,
            )

        db.commit()
        db.refresh(pub_record)
        return pub_record

    def verify_external_publication(
        self,
        db: Session,
        application_id: str,
        version: Optional[str] = None,
        publication_id: Optional[str] = None,
        actor: str = "operator",
    ) -> PublicationRecord:
        """Query AgentGen Pro to verify pending or unknown publication status."""
        app = ApplicationService.get_application(db, application_id)
        target_version = version or app.current_version

        query = db.query(PublicationRecord).filter(
            PublicationRecord.application_id == app.application_id,
            PublicationRecord.application_version == target_version,
        )
        if publication_id:
            query = query.filter(PublicationRecord.publication_id == publication_id)

        pub_record = query.order_by(PublicationRecord.created_at.desc(), PublicationRecord.id.desc()).first()
        if not pub_record:
            raise PublicationNotFoundError(f"{application_id}:{target_version}")

        # Check external status
        ext_res = self.publication_client.check_publication_status(
            application_id=pub_record.application_id,
            version=pub_record.application_version,
            external_publication_id=pub_record.external_publication_id,
        )

        if ext_res.status == "PUBLISHED":
            pub_record.status = PublicationStatusEnum.PUBLISHED.value
            pub_record.external_status = "PUBLISHED"
            pub_record.confirmed_at = datetime.now(timezone.utc)
            if ext_res.confirmation_details:
                pub_record.external_confirmation = ext_res.confirmation_details
            EvidenceService.record_audit_event(
                db=db,
                event_type="PUBLICATION_CONFIRMED",
                actor=actor,
                event_data={
                    "publication_id": pub_record.publication_id,
                    "external_publication_id": pub_record.external_publication_id,
                },
                certification_id=pub_record.certification_id,
            )
        elif ext_res.status == "FAILED":
            pub_record.status = PublicationStatusEnum.PUBLICATION_FAILED.value
            pub_record.error_code = ext_res.error_code
            pub_record.error_message = ext_res.error_message
            EvidenceService.record_audit_event(
                db=db,
                event_type="PUBLICATION_FAILED",
                actor=actor,
                event_data={"publication_id": pub_record.publication_id, "error": ext_res.error_message},
                certification_id=pub_record.certification_id,
            )

        db.commit()
        db.refresh(pub_record)
        return pub_record
