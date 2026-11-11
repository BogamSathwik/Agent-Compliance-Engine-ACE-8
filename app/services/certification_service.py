"""Certification service orchestrating compliance runs across all 10 stages."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.context import CertificationContext
from app.models.certification import (
    CertificationRun,
    CertificationStatusEnum,
    TriggerTypeEnum,
)
from app.models.certification_check import (
    CertificationCheck,
    CheckTypeEnum,
    CheckStatusEnum,
)
from app.models.finding import (
    CertificationFinding,
    FindingCategoryEnum,
    FindingStatusEnum,
    FindingSeverityEnum,
    RemediationStatusEnum,
)
from app.models.evidence import SourceSystemEnum
from app.schemas.certification import CertificationCreate, FindingsSummary
from app.core.exceptions import (
    CertificationNotFoundError,
    CertificationAlreadyRunningError,
    ACEException,
)
from app.core.security import generate_secure_id
from app.core.logging import get_logger
from app.services.application_service import ApplicationService
from app.services.evidence_service import EvidenceService
from app.services.version_consistency_service import VersionConsistencyService
from app.services.policy_engine import PolicyEngine
from app.services.remediation_service import RemediationService
from app.integrations.contracts import (
    DocumentVerifierProtocol,
    QAVerifierProtocol,
    RuleEngineVerifierProtocol,
    Phase1DocumentVerifierPlaceholder,
    Phase1QAVerifierPlaceholder,
    Phase1RuleEngineVerifierPlaceholder,
    MANDATORY_17_DOC_CATEGORIES,
    DocumentCategoryVerification,
    DocumentVerificationResult,
    QAVerificationResult,
    RuleEvaluationResult,
)
from app.integrations.rag_client import MyBlocksRAGClient
from app.integrations.qa_client import MyBlocksQAClient
from app.integrations.rule_client import AgentRuleEvaluationClient

from app.core.config import get_settings

settings = get_settings()
logger = get_logger("ace.certification_service")


class InvalidStatusTransitionError(ACEException):
    def __init__(self, current_status: str, target_status: str):
        super().__init__(
            message=f"Cannot transition certification status from '{current_status}' to '{target_status}'.",
            code="INVALID_STATUS_TRANSITION",
            status_code=409,
            details={"current_status": current_status, "target_status": target_status},
        )


class CertificationService:
    """Orchestrates compliance evaluation across all 10 explicit pipeline stages."""

    def __init__(
        self,
        document_verifier: Optional[DocumentVerifierProtocol] = None,
        qa_verifier: Optional[QAVerifierProtocol] = None,
        rule_verifier: Optional[RuleEngineVerifierProtocol] = None,
    ):
        self.document_verifier = document_verifier or MyBlocksRAGClient()
        self.qa_verifier = qa_verifier or MyBlocksQAClient()
        self.rule_verifier = rule_verifier or AgentRuleEvaluationClient()

    def create_certification_run(
        self, db: Session, cert_in: CertificationCreate
    ) -> CertificationRun:
        """Stage 1: Validate, create CertificationContext, and queue a new certification run.

        Includes idempotency guard against duplicate submission events.
        """
        app = ApplicationService.get_application(db, cert_in.application_id)
        target_version = cert_in.version or app.current_version

        # Fetch or link ApplicationVersion record
        app_version_record = (
            db.query(ApplicationService.get_application_version.__annotations__["return"])
            if False else None
        )
        try:
            app_ver = ApplicationService.get_application_version(db, app.application_id, target_version)
            app_version_id = app_ver.id
        except Exception:
            app_version_id = None

        # Idempotency guard: if submission_id is provided, check for existing or active runs safely
        if cert_in.submission_id:
            if cert_in.trigger_type != TriggerTypeEnum.RE_CERTIFICATION:
                existing_sub_run = (
                    db.query(CertificationRun)
                    .filter(
                        CertificationRun.application_id == app.application_id,
                        CertificationRun.application_version == target_version,
                        CertificationRun.submission_id == cert_in.submission_id,
                    )
                    .order_by(CertificationRun.created_at.desc(), CertificationRun.id.desc())
                    .first()
                )
                if existing_sub_run:
                    logger.info(
                        f"Idempotent request matched existing run {existing_sub_run.certification_id}",
                        extra={
                            "event": "idempotent_certification_matched",
                            "certification_id": existing_sub_run.certification_id,
                            "submission_id": cert_in.submission_id,
                        },
                    )
                    return existing_sub_run
            else:
                active_sub_run = (
                    db.query(CertificationRun)
                    .filter(
                        CertificationRun.application_id == app.application_id,
                        CertificationRun.application_version == target_version,
                        CertificationRun.submission_id == cert_in.submission_id,
                        CertificationRun.status.in_([
                            CertificationStatusEnum.QUEUED.value,
                            CertificationStatusEnum.RUNNING.value,
                        ]),
                    )
                    .first()
                )
                if active_sub_run:
                    return active_sub_run

        # General active certification guard
        active_run = (
            db.query(CertificationRun)
            .filter(
                CertificationRun.application_id == app.application_id,
                CertificationRun.application_version == target_version,
                CertificationRun.status.in_([
                    CertificationStatusEnum.QUEUED.value,
                    CertificationStatusEnum.RUNNING.value,
                ]),
            )
            .first()
        )
        if active_run:
            raise CertificationAlreadyRunningError(app.application_id, target_version)

        cert_id = generate_secure_id("CERT", 12)
        trigger_val = (
            cert_in.trigger_type.value
            if isinstance(cert_in.trigger_type, TriggerTypeEnum)
            else str(cert_in.trigger_type or "MANUAL")
        )

        run = CertificationRun(
            certification_id=cert_id,
            application_id=app.application_id,
            application_version_id=app_version_id,
            application_version=target_version,
            commit_hash=cert_in.commit_hash,
            submission_id=cert_in.submission_id,
            status=CertificationStatusEnum.QUEUED.value,
            trigger_type=trigger_val,
            policy_version=cert_in.policy_version or "v1.0",
        )

        db.add(run)
        db.commit()
        db.refresh(run)

        # Audit event
        EvidenceService.record_audit_event(
            db=db,
            event_type="CERTIFICATION_CREATED",
            actor="api_client",
            event_data={
                "certification_id": run.certification_id,
                "application_id": run.application_id,
                "version": run.application_version,
                "commit_hash": run.commit_hash,
                "submission_id": run.submission_id,
                "trigger_type": run.trigger_type,
            },
            certification_id=run.certification_id,
        )

        logger.info(
            f"Certification queued: {run.certification_id}",
            extra={
                "event": "certification_queued",
                "certification_id": run.certification_id,
                "application_id": run.application_id,
                "version": run.application_version,
                "submission_id": run.submission_id,
            },
        )

        # Dispatch execution based on configured mode
        curr_settings = get_settings()
        if (curr_settings.EXECUTION_MODE == "async" or getattr(curr_settings, "TESTING", False)) and not curr_settings.CELERY_ALWAYS_EAGER:
            try:
                from app.workers.certification_worker import run_certification_task
                task_res = run_certification_task.delay(run.certification_id)
                logger.info(
                    f"Celery task dispatched: {getattr(task_res, 'id', 'N/A')} for cert {run.certification_id}",
                    extra={
                        "event": "celery_task_dispatched",
                        "certification_id": run.certification_id,
                        "task_id": getattr(task_res, "id", None),
                    },
                )
            except Exception as exc:
                if curr_settings.ENVIRONMENT == "production":
                    logger.error(
                        f"Celery task dispatch failed in production: {exc}",
                        extra={
                            "event": "celery_dispatch_failed",
                            "certification_id": run.certification_id,
                            "error": str(exc),
                        },
                    )
                    run.status = CertificationStatusEnum.ERROR.value
                    db.commit()
                    from app.core.exceptions import BackgroundJobError
                    raise BackgroundJobError(f"Celery broker unavailable: {exc}")
                elif not getattr(curr_settings, "TESTING", False):
                    logger.info(
                        f"Celery broker unavailable in local development. Executing synchronously as configured: {exc}",
                        extra={
                            "event": "local_sync_execution_fallback",
                            "certification_id": run.certification_id,
                        },
                    )
                    self.execute_certification_pipeline(db, run.certification_id)
        elif curr_settings.EXECUTION_MODE == "sync" and not getattr(curr_settings, "TESTING", False):
            # Explicit synchronous execution mode (development or Celery eager)
            logger.info(
                f"Executing certification synchronously (EXECUTION_MODE={curr_settings.EXECUTION_MODE}, ALWAYS_EAGER={curr_settings.CELERY_ALWAYS_EAGER})",
                extra={
                    "event": "sync_certification_execution",
                    "certification_id": run.certification_id,
                },
            )
            self.execute_certification_pipeline(db, run.certification_id)

        return run

    def request_recertification(
        self,
        db: Session,
        application_id: str,
        certification_id: Optional[str] = None,
        version: Optional[str] = None,
        submission_id: Optional[str] = None,
        commit_hash: Optional[str] = None,
        actor: str = "operator",
    ) -> CertificationRun:
        """Create a distinct re-certification run preserving prior runs and audit history."""
        app = ApplicationService.get_application(db, application_id)
        target_version = version or app.current_version

        prior_run = None
        if certification_id:
            prior_run = (
                db.query(CertificationRun)
                .filter(CertificationRun.certification_id == certification_id)
                .first()
            )
            if prior_run:
                target_version = version or prior_run.application_version
                commit_hash = commit_hash or prior_run.commit_hash
                submission_id = submission_id or prior_run.submission_id

        cert_in = CertificationCreate(
            application_id=app.application_id,
            version=target_version,
            commit_hash=commit_hash,
            submission_id=submission_id,
            trigger_type=TriggerTypeEnum.RE_CERTIFICATION,
        )

        new_run = self.create_certification_run(db, cert_in)

        EvidenceService.record_audit_event(
            db=db,
            event_type="RE_CERTIFICATION_REQUESTED",
            actor=actor,
            event_data={
                "application_id": app.application_id,
                "version": target_version,
                "prior_certification_id": prior_run.certification_id if prior_run else None,
                "new_certification_id": new_run.certification_id,
                "submission_id": submission_id,
            },
            certification_id=new_run.certification_id,
        )

        return new_run

    @staticmethod
    def get_certification(
        db: Session, certification_id: str
    ) -> Tuple[CertificationRun, FindingsSummary]:
        """Fetch certification run and calculate findings summary."""
        run = (
            db.query(CertificationRun)
            .filter(CertificationRun.certification_id == certification_id)
            .first()
        )
        if not run:
            raise CertificationNotFoundError(certification_id)

        findings = (
            db.query(CertificationFinding)
            .filter(CertificationFinding.certification_id == certification_id)
            .all()
        )

        summary = FindingsSummary(
            total=len(findings),
            passed=sum(1 for f in findings if f.status == FindingStatusEnum.PASS.value),
            failed=sum(1 for f in findings if f.status == FindingStatusEnum.FAIL.value),
            not_verified=sum(1 for f in findings if f.status == FindingStatusEnum.NOT_VERIFIED.value),
            partial=sum(1 for f in findings if f.status == FindingStatusEnum.PARTIAL.value),
        )

        return run, summary

    @staticmethod
    def get_findings(
        db: Session, certification_id: str
    ) -> List[CertificationFinding]:
        """Retrieve all findings for a given certification run."""
        CertificationService.get_certification(db, certification_id)
        return (
            db.query(CertificationFinding)
            .filter(CertificationFinding.certification_id == certification_id)
            .order_by(CertificationFinding.id.asc())
            .all()
        )

    @staticmethod
    def get_checks(
        db: Session, certification_id: str
    ) -> List[CertificationCheck]:
        """Retrieve all checks for a given certification run."""
        CertificationService.get_certification(db, certification_id)
        return (
            db.query(CertificationCheck)
            .filter(CertificationCheck.certification_id == certification_id)
            .order_by(CertificationCheck.id.asc())
            .all()
        )

    @staticmethod
    def evaluate_policy(findings: List[CertificationFinding]) -> CertificationStatusEnum:
        """Backward compatible helper evaluating findings list."""
        if not findings:
            return CertificationStatusEnum.NOT_READY
        if any(f.status != FindingStatusEnum.PASS.value for f in findings):
            return CertificationStatusEnum.NOT_READY
        return CertificationStatusEnum.READY_TO_PUBLISH

    @staticmethod
    def _call_verifier_safely(verifier_fn, **kwargs):
        """Invoke a verifier protocol implementation with only parameters it accepts."""
        import inspect
        sig = inspect.signature(verifier_fn)
        call_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return verifier_fn(**call_kwargs)

    @staticmethod
    def _build_failed_doc_result(context: CertificationContext, error_msg: str) -> DocumentVerificationResult:
        cat_verifications = [
            DocumentCategoryVerification(
                category=cat,
                requirement_id=f"DOC-{cat.replace('_', '-')}",
                status=FindingStatusEnum.NOT_VERIFIED,
                title=f"Document Requirement: {cat} (Unavailable)",
                description=f"MyBlocks RAG document verification unavailable for category '{cat}': {error_msg}",
                remediation=f"Ensure MyBlocks RAG service is running and accessible, then re-index category '{cat}'.",
                source_version=context.application_version,
                raw_evidence={"error": error_msg, "integration": "MYBLOCKS_RAG"},
            )
            for cat in MANDATORY_17_DOC_CATEGORIES
        ]
        return DocumentVerificationResult(
            status=FindingStatusEnum.NOT_VERIFIED,
            category=FindingCategoryEnum.DOCUMENT,
            required_count=len(MANDATORY_17_DOC_CATEGORIES),
            verified_count=0,
            missing_categories=list(MANDATORY_17_DOC_CATEGORIES),
            title="MyBlocks RAG Document Verification Unavailable",
            description=f"MyBlocks RAG service is unavailable or encountered an error: {error_msg}",
            remediation="Check MyBlocks RAG service availability and configuration, then retry certification.",
            raw_evidence={"error": error_msg, "integration": "MYBLOCKS_RAG"},
            external_run_id=f"RAG-ERR-{context.certification_id}",
            external_application_id=context.application_id,
            external_version=context.application_version,
            category_verifications=cat_verifications,
        )

    @staticmethod
    def _build_failed_qa_result(context: CertificationContext, error_msg: str) -> QAVerificationResult:
        return QAVerificationResult(
            status=FindingStatusEnum.NOT_VERIFIED,
            category=FindingCategoryEnum.QA,
            passed=False,
            title="MyBlocks QA Test Suite Verification Unavailable",
            description=f"MyBlocks QA service is unavailable or encountered an error: {error_msg}",
            remediation="Verify MyBlocks QA service availability and network connectivity, then retry verification.",
            raw_evidence={"error": error_msg, "integration": "MYBLOCKS_QA"},
            external_run_id=f"QA-ERR-{context.certification_id}",
            external_application_id=context.application_id,
            external_version=context.application_version,
        )

    @staticmethod
    def _build_failed_rule_result(context: CertificationContext, error_msg: str) -> RuleEvaluationResult:
        return RuleEvaluationResult(
            status=FindingStatusEnum.NOT_VERIFIED,
            category=FindingCategoryEnum.RULE,
            total_rules=9,
            passed_rules=0,
            failed_rules=0,
            passed=False,
            title="9-Rule Agent Compliance Evaluation Unavailable",
            description=f"9-Rule agent scanner is unavailable or encountered an error: {error_msg}",
            remediation="Verify 9-Rule Agent Evaluation service availability and configuration, then retry evaluation.",
            raw_evidence={"error": error_msg, "integration": "RULE_ENGINE"},
            external_run_id=f"RULE-ERR-{context.certification_id}",
            external_application_id=context.application_id,
            external_version=context.application_version,
        )

    def execute_certification_pipeline(
        self, db: Session, certification_id: str
    ) -> CertificationRun:
        """Execute the 10-stage certification pipeline with state check concurrency protection."""
        # Controlled state transition check: only QUEUED can transition to RUNNING
        run = (
            db.query(CertificationRun)
            .filter(CertificationRun.certification_id == certification_id)
            .first()
        )
        if not run:
            raise CertificationNotFoundError(certification_id)

        if run.status != CertificationStatusEnum.QUEUED.value:
            raise InvalidStatusTransitionError(run.status, CertificationStatusEnum.RUNNING.value)

        # Stage 1: Build typed CertificationContext
        context = CertificationContext(
            certification_id=run.certification_id,
            application_id=run.application_id,
            application_version=run.application_version,
            commit_hash=run.commit_hash,
            submission_id=run.submission_id,
            trigger_type=run.trigger_type,
            policy_version=run.policy_version,
            application_version_id=run.application_version_id,
        )

        # Transition status to RUNNING
        run.status = CertificationStatusEnum.RUNNING.value
        run.started_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)

        EvidenceService.record_audit_event(
            db=db,
            event_type="CERTIFICATION_STARTED",
            actor="certification_worker",
            event_data={"certification_id": run.certification_id, "started_at": run.started_at.isoformat()},
            certification_id=run.certification_id,
        )

        try:
            return self._execute_pipeline_stages(db, run, context)
        except Exception as exc:
            logger.error(
                f"Unexpected runtime failure in certification pipeline for {run.certification_id}: {exc}",
                exc_info=True,
                extra={"event": "certification_pipeline_failed", "certification_id": run.certification_id},
            )
            run.status = CertificationStatusEnum.ERROR.value
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(run)
            EvidenceService.record_audit_event(
                db=db,
                event_type="CERTIFICATION_ERROR",
                actor="certification_worker",
                event_data={"certification_id": run.certification_id, "error": str(exc)},
                certification_id=run.certification_id,
            )
            raise

    def _execute_pipeline_stages(
        self, db: Session, run: CertificationRun, context: CertificationContext
    ) -> CertificationRun:
        settings = get_settings()
        # Stage 2: Create Certification Checks
        checks: List[CertificationCheck] = []
        check_configs = [
            ("CHK-DOC-001", CheckTypeEnum.DOCUMENT, "MyBlocks RAG Document Verification", "MYBLOCKS_RAG"),
            ("CHK-QA-001", CheckTypeEnum.QA, "MyBlocks QA Authoritative Test Suite", "MYBLOCKS_QA"),
            ("CHK-RULE-001", CheckTypeEnum.AGENT_RULES, "9-Rule Agent Governance Evaluation", "RULE_ENGINE"),
            ("CHK-VER-001", CheckTypeEnum.VERSION, "Cross-Subsystem Version Consistency", "ACE"),
        ]

        for cid, ctype, cname, csource in check_configs:
            chk = CertificationCheck(
                certification_id=run.certification_id,
                check_id=cid,
                check_type=ctype.value,
                check_name=cname,
                source_system=csource,
                status=CheckStatusEnum.PENDING.value,
            )
            db.add(chk)
            checks.append(chk)

        db.commit()

        for chk in checks:
            EvidenceService.record_audit_event(
                db=db,
                event_type="CHECK_CREATED",
                actor="certification_service",
                event_data={"check_id": chk.check_id, "check_type": chk.check_type},
                certification_id=run.certification_id,
            )

        findings: List[CertificationFinding] = []
        doc_chk = next(c for c in checks if c.check_id == "CHK-DOC-001")
        qa_chk = next(c for c in checks if c.check_id == "CHK-QA-001")
        rule_chk = next(c for c in checks if c.check_id == "CHK-RULE-001")
        ver_chk = next(c for c in checks if c.check_id == "CHK-VER-001")

        # Stage 3, 4, 5: Verification, Evidence Collection, Findings for Subsystems

        # Step 3A: Document Verification (MyBlocks RAG across all 17 categories)
        doc_chk.status = CheckStatusEnum.RUNNING.value
        doc_chk.started_at = datetime.now(timezone.utc)
        db.commit()

        doc_error = None
        try:
            doc_result = self._call_verifier_safely(
                self.document_verifier.verify_application_documents,
                application_id=context.application_id,
                version=context.application_version,
                commit_hash=context.commit_hash,
                submission_id=context.submission_id,
                certification_id=context.certification_id,
            )
            if not doc_result:
                doc_result = self._build_failed_doc_result(context, "Document verifier returned null response")
        except Exception as exc:
            logger.warning(
                f"Document verifier raised exception: {exc}",
                extra={"event": "rag_verifier_exception", "error": str(exc), "certification_id": run.certification_id},
            )
            doc_error = str(exc)
            doc_result = self._build_failed_doc_result(context, doc_error)

        doc_chk.status = (
            CheckStatusEnum.PASS.value if doc_result.status == FindingStatusEnum.PASS
            else CheckStatusEnum.FAIL.value if doc_result.status == FindingStatusEnum.FAIL
            else CheckStatusEnum.NOT_VERIFIED.value
        )
        if doc_error:
            doc_chk.error_code = "SERVICE_UNAVAILABLE"
            doc_chk.error_message = doc_error
        doc_chk.completed_at = datetime.now(timezone.utc)

        # Build findings and evidence for all 17 document categories
        category_vers = doc_result.category_verifications
        if not category_vers:
            category_vers = [
                DocumentCategoryVerification(
                    category=cat,
                    requirement_id=f"DOC-{cat.replace('_', '-')}",
                    status=FindingStatusEnum.NOT_VERIFIED,
                    title=f"Document Requirement: {cat}",
                    description=f"Category '{cat}' is not verified in MyBlocks RAG.",
                    remediation=f"Ingest and verify category '{cat}' in MyBlocks RAG for {context.application_id} v{context.application_version}.",
                    source_version=context.application_version,
                )
                for cat in MANDATORY_17_DOC_CATEGORIES
            ]

        for cat_ver in category_vers:
            cat_finding = CertificationFinding(
                certification_id=run.certification_id,
                check_id=doc_chk.check_id,
                requirement_id=cat_ver.requirement_id,
                finding_code=f"FINDING-DOC-{cat_ver.category}",
                category=FindingCategoryEnum.DOCUMENT.value,
                status=cat_ver.status.value,
                remediation_status=(
                    RemediationStatusEnum.RESOLVED.value
                    if cat_ver.status == FindingStatusEnum.PASS
                    else RemediationStatusEnum.OPEN.value
                ),
                severity=(
                    FindingSeverityEnum.HIGH.value
                    if cat_ver.status != FindingStatusEnum.PASS
                    else FindingSeverityEnum.LOW.value
                ),
                title=cat_ver.title,
                description=cat_ver.description,
                remediation=cat_ver.remediation,
            )
            db.add(cat_finding)
            findings.append(cat_finding)
            db.commit()
            db.refresh(cat_finding)

            cat_ev_data = dict(cat_ver.raw_evidence) if cat_ver.raw_evidence else {
                "category": cat_ver.category,
                "requirement_id": cat_ver.requirement_id,
                "status": cat_ver.status.value,
                "title": cat_ver.title,
                "description": cat_ver.description,
                "source_version": cat_ver.source_version or context.application_version,
            }

            EvidenceService.record_evidence(
                db=db,
                certification_id=run.certification_id,
                check_id=doc_chk.check_id,
                finding_id=cat_finding.id,
                source_system=SourceSystemEnum.MYBLOCKS_RAG,
                source_reference=cat_ver.source_reference or f"rag-doc://{context.application_id}/{context.application_version}/{cat_ver.category}",
                evidence_type="DOCUMENT_CATEGORY_VERIFICATION",
                evidence_data=cat_ev_data,
                source_version=cat_ver.source_version or context.application_version,
                source_run_id=cat_ver.source_run_id or doc_result.external_run_id or f"RAG-RUN-{run.certification_id}",
                source_timestamp=cat_ver.source_timestamp or datetime.now(timezone.utc),
                hash=cat_ver.hash,
                confidence=cat_ver.confidence,
            )

        EvidenceService.record_integration_run(
            db=db,
            certification_id=run.certification_id,
            source_system="MYBLOCKS_RAG",
            operation="verify_application_documents",
            status=doc_chk.status,
            external_application_id=doc_result.external_application_id or context.application_id,
            external_version=doc_result.external_version or context.application_version,
            external_run_id=doc_result.external_run_id or f"RAG-RUN-{run.certification_id}",
            started_at=doc_chk.started_at,
            completed_at=doc_chk.completed_at,
            response_metadata=doc_result.raw_evidence or {"status": doc_chk.status},
            error_code=doc_chk.error_code,
            error_message=doc_chk.error_message,
        )

        # Step 3B: QA Verification (Deferred post-upload to AgentGen)
        qa_chk.status = CheckStatusEnum.RUNNING.value
        qa_chk.started_at = datetime.now(timezone.utc)
        db.commit()

        if settings.DEFER_QA_UNTIL_POST_UPLOAD:
            logger.info(
                f"QA verification deferred until post-upload to AgentGen for {context.application_id} (v{context.application_version}). Scheduled within {settings.QA_SCHEDULE_WINDOW_DAYS} days.",
                extra={"event": "qa_deferred_post_upload", "certification_id": run.certification_id},
            )
            qa_chk.status = CheckStatusEnum.PASS.value
            qa_chk.check_name = f"MyBlocks QA Test Suite (Scheduled Post-Upload: {settings.QA_SCHEDULE_WINDOW_DAYS}-Day Window)"
            qa_chk.completed_at = datetime.now(timezone.utc)

            qa_finding = CertificationFinding(
                certification_id=run.certification_id,
                check_id=qa_chk.check_id,
                requirement_id="QA-SUITE-V1",
                finding_code="FINDING-QA-001",
                category=FindingCategoryEnum.QA.value,
                status=FindingStatusEnum.PASS.value,
                remediation_status=RemediationStatusEnum.RESOLVED.value,
                severity=FindingSeverityEnum.INFO.value,
                title="QA Verification Scheduled Post-Upload",
                description=(
                    f"QA automated test suite execution is scheduled within a {settings.QA_SCHEDULE_WINDOW_DAYS}-day "
                    "window following successful upload to AgentGen Pro."
                ),
                remediation="Execute post-upload QA test suite in MyBlocks QA within 1 week of AgentGen upload.",
            )
            db.add(qa_finding)
            findings.append(qa_finding)
            db.commit()
            db.refresh(qa_finding)

            qa_ev_data = {
                "application_id": context.application_id,
                "version": context.application_version,
                "status": "SCHEDULED_POST_UPLOAD",
                "schedule_window_days": settings.QA_SCHEDULE_WINDOW_DAYS,
                "scheduled_at": datetime.now(timezone.utc).isoformat(),
                "title": "QA Verification Scheduled Post-Upload",
                "description": f"QA verification scheduled within {settings.QA_SCHEDULE_WINDOW_DAYS} days after AgentGen Pro upload.",
            }

            EvidenceService.record_evidence(
                db=db,
                certification_id=run.certification_id,
                check_id=qa_chk.check_id,
                finding_id=qa_finding.id,
                source_system=SourceSystemEnum.MYBLOCKS_QA,
                source_reference=f"qa-scheduled://{context.application_id}/{context.application_version}",
                evidence_type="QA_POST_UPLOAD_SCHEDULE",
                evidence_data=qa_ev_data,
                source_version=context.application_version,
                source_run_id=f"QA-SCHED-{run.certification_id}",
                source_timestamp=datetime.now(timezone.utc),
            )

            EvidenceService.record_integration_run(
                db=db,
                certification_id=run.certification_id,
                source_system="MYBLOCKS_QA",
                operation="schedule_post_upload_qa",
                status=qa_chk.status,
                external_application_id=context.application_id,
                external_version=context.application_version,
                external_run_id=f"QA-SCHED-{run.certification_id}",
                started_at=qa_chk.started_at,
                completed_at=qa_chk.completed_at,
                response_metadata=qa_ev_data,
            )
            qa_external_app_id = context.application_id
            qa_external_version = context.application_version
        else:
            qa_error = None
            try:
                qa_result = self._call_verifier_safely(
                    self.qa_verifier.verify_application_qa,
                    application_id=context.application_id,
                    version=context.application_version,
                    commit_hash=context.commit_hash,
                    submission_id=context.submission_id,
                    certification_id=context.certification_id,
                )
                if not qa_result:
                    qa_result = self._build_failed_qa_result(context, "QA verifier returned null response")
            except Exception as exc:
                logger.warning(
                    f"QA verifier raised exception: {exc}",
                    extra={"event": "qa_verifier_exception", "error": str(exc), "certification_id": run.certification_id},
                )
                qa_error = str(exc)
                qa_result = self._build_failed_qa_result(context, qa_error)

            qa_chk.status = (
                CheckStatusEnum.PASS.value if qa_result.status == FindingStatusEnum.PASS
                else CheckStatusEnum.FAIL.value if qa_result.status == FindingStatusEnum.FAIL
                else CheckStatusEnum.NOT_VERIFIED.value
            )
            if qa_error:
                qa_chk.error_code = "SERVICE_UNAVAILABLE"
                qa_chk.error_message = qa_error
            qa_chk.completed_at = datetime.now(timezone.utc)

            qa_finding = CertificationFinding(
                certification_id=run.certification_id,
                check_id=qa_chk.check_id,
                requirement_id="QA-SUITE-V1",
                finding_code="FINDING-QA-001",
                category=FindingCategoryEnum.QA.value,
                status=qa_result.status.value,
                remediation_status=(
                    RemediationStatusEnum.RESOLVED.value
                    if qa_result.status == FindingStatusEnum.PASS
                    else RemediationStatusEnum.OPEN.value
                ),
                severity=(
                    FindingSeverityEnum.CRITICAL.value
                    if qa_result.status != FindingStatusEnum.PASS
                    else FindingSeverityEnum.LOW.value
                ),
                title=qa_result.title,
                description=qa_result.description,
                remediation=qa_result.remediation,
            )
            db.add(qa_finding)
            findings.append(qa_finding)
            db.commit()
            db.refresh(qa_finding)

            qa_ev_data = dict(qa_result.raw_evidence) if qa_result.raw_evidence else {
                "application_id": qa_result.external_application_id or context.application_id,
                "version": qa_result.external_version or context.application_version,
                "status": qa_result.status.value,
                "passed": qa_result.passed,
                "pass_count": qa_result.pass_count,
                "fail_count": qa_result.fail_count,
                "critical_failures": qa_result.critical_failures,
                "title": qa_result.title,
                "description": qa_result.description,
                "external_run_id": qa_result.external_run_id or f"QA-RUN-{run.certification_id}",
            }

            EvidenceService.record_evidence(
                db=db,
                certification_id=run.certification_id,
                check_id=qa_chk.check_id,
                finding_id=qa_finding.id,
                source_system=SourceSystemEnum.MYBLOCKS_QA,
                source_reference=qa_result.source_reference or f"qa-suite://{context.application_id}/{context.application_version}",
                evidence_type="QA_TEST_RUN_REPORT",
                evidence_data=qa_ev_data,
                source_version=qa_result.external_version or context.application_version,
                source_run_id=qa_result.external_run_id or f"QA-RUN-{run.certification_id}",
                source_timestamp=qa_result.execution_timestamp or datetime.now(timezone.utc),
                confidence=qa_result.confidence,
                hash=qa_result.hash,
            )

            EvidenceService.record_integration_run(
                db=db,
                certification_id=run.certification_id,
                source_system="MYBLOCKS_QA",
                operation="verify_application_qa",
                status=qa_chk.status,
                external_application_id=qa_result.external_application_id or context.application_id,
                external_version=qa_result.external_version or context.application_version,
                external_run_id=qa_result.external_run_id or f"QA-RUN-{run.certification_id}",
                started_at=qa_chk.started_at,
                completed_at=qa_chk.completed_at,
                response_metadata=qa_result.raw_evidence or {"status": qa_chk.status},
                error_code=qa_chk.error_code,
                error_message=qa_chk.error_message,
            )
            qa_external_app_id = qa_result.external_application_id or context.application_id
            qa_external_version = qa_result.external_version or context.application_version

        # Step 3C: Rule Engine Verification (9 Rules)
        rule_chk.status = CheckStatusEnum.RUNNING.value
        rule_chk.started_at = datetime.now(timezone.utc)
        db.commit()

        rule_error = None
        try:
            rule_result = self._call_verifier_safely(
                self.rule_verifier.evaluate_agent_rules,
                application_id=context.application_id,
                version=context.application_version,
                commit_hash=context.commit_hash,
                submission_id=context.submission_id,
                certification_id=context.certification_id,
            )
            if not rule_result:
                rule_result = self._build_failed_rule_result(context, "Rule verifier returned null response")
        except Exception as exc:
            logger.warning(
                f"Rule verifier raised exception: {exc}",
                extra={"event": "rule_verifier_exception", "error": str(exc), "certification_id": run.certification_id},
            )
            rule_error = str(exc)
            rule_result = self._build_failed_rule_result(context, rule_error)

        rule_chk.status = (
            CheckStatusEnum.PASS.value if rule_result.status == FindingStatusEnum.PASS
            else CheckStatusEnum.FAIL.value if rule_result.status == FindingStatusEnum.FAIL
            else CheckStatusEnum.NOT_VERIFIED.value
        )
        if rule_error:
            rule_chk.error_code = "SERVICE_UNAVAILABLE"
            rule_chk.error_message = rule_error
        rule_chk.completed_at = datetime.now(timezone.utc)

        rule_finding = CertificationFinding(
            certification_id=run.certification_id,
            check_id=rule_chk.check_id,
            requirement_id="RULE-SET-9",
            finding_code="FINDING-RULE-001",
            category=FindingCategoryEnum.RULE.value,
            status=rule_result.status.value,
            remediation_status=(
                RemediationStatusEnum.RESOLVED.value
                if rule_result.status == FindingStatusEnum.PASS
                else RemediationStatusEnum.OPEN.value
            ),
            severity=(
                FindingSeverityEnum.CRITICAL.value
                if rule_result.status != FindingStatusEnum.PASS
                else FindingSeverityEnum.LOW.value
            ),
            title=rule_result.title,
            description=rule_result.description,
            remediation=rule_result.remediation,
        )
        db.add(rule_finding)
        findings.append(rule_finding)
        db.commit()
        db.refresh(rule_finding)

        rule_ev_data = dict(rule_result.raw_evidence) if rule_result.raw_evidence else {
            "application_id": rule_result.external_application_id or context.application_id,
            "version": rule_result.external_version or context.application_version,
            "status": rule_result.status.value,
            "passed": rule_result.passed,
            "total_rules": rule_result.total_rules,
            "passed_rules": rule_result.passed_rules,
            "failed_rules": rule_result.failed_rules,
            "title": rule_result.title,
            "description": rule_result.description,
            "external_run_id": rule_result.external_run_id or f"RULE-SCAN-{run.certification_id}",
        }

        EvidenceService.record_evidence(
            db=db,
            certification_id=run.certification_id,
            check_id=rule_chk.check_id,
            finding_id=rule_finding.id,
            source_system=SourceSystemEnum.RULE_ENGINE,
            source_reference=rule_result.source_reference or f"nine-rules://{context.application_id}/{context.application_version}",
            evidence_type="RULE_EVALUATION_REPORT",
            evidence_data=rule_ev_data,
            source_version=rule_result.external_version or context.application_version,
            source_run_id=rule_result.external_run_id or f"RULE-SCAN-{run.certification_id}",
            source_timestamp=rule_result.execution_timestamp or datetime.now(timezone.utc),
            confidence=rule_result.confidence,
            hash=rule_result.hash,
        )

        EvidenceService.record_integration_run(
            db=db,
            certification_id=run.certification_id,
            source_system="RULE_ENGINE",
            operation="evaluate_agent_rules",
            status=rule_chk.status,
            external_application_id=rule_result.external_application_id or context.application_id,
            external_version=rule_result.external_version or context.application_version,
            external_run_id=rule_result.external_run_id or f"RULE-SCAN-{run.certification_id}",
            started_at=rule_chk.started_at,
            completed_at=rule_chk.completed_at,
            response_metadata=rule_result.raw_evidence or {"status": rule_chk.status},
            error_code=rule_chk.error_code,
            error_message=rule_chk.error_message,
        )

        # Stage 6: Verify Consistency (VersionConsistencyService)
        ver_chk.status = CheckStatusEnum.RUNNING.value
        ver_chk.started_at = datetime.now(timezone.utc)
        db.commit()

        # Gather reported identities from external verification runs
        external_identity_reports = [
            {
                "source_system": "MYBLOCKS_RAG",
                "application_id": doc_result.external_application_id or context.application_id,
                "version": doc_result.external_version or context.application_version,
            },
            {
                "source_system": "MYBLOCKS_QA",
                "application_id": qa_external_app_id,
                "version": qa_external_version,
            },
            {
                "source_system": "RULE_ENGINE",
                "application_id": rule_result.external_application_id or context.application_id,
                "version": rule_result.external_version or context.application_version,
            },
        ]
        consistency_report = VersionConsistencyService.verify_consistency(context, external_identity_reports)

        ver_chk.status = (
            CheckStatusEnum.PASS.value if consistency_report.is_consistent
            else CheckStatusEnum.NOT_VERIFIED.value
        )
        ver_chk.completed_at = datetime.now(timezone.utc)

        ver_finding = CertificationFinding(
            certification_id=run.certification_id,
            check_id=ver_chk.check_id,
            requirement_id="VER-CONSISTENCY",
            finding_code="FINDING-VER-001",
            category=FindingCategoryEnum.VERSION.value,
            status=consistency_report.status.value,
            remediation_status=(
                RemediationStatusEnum.RESOLVED.value
                if consistency_report.status == FindingStatusEnum.PASS
                else RemediationStatusEnum.OPEN.value
            ),
            severity=FindingSeverityEnum.MEDIUM.value if consistency_report.is_consistent else FindingSeverityEnum.CRITICAL.value,
            title=consistency_report.title,
            description=consistency_report.description,
            remediation=consistency_report.remediation,
        )
        db.add(ver_finding)
        findings.append(ver_finding)
        db.commit()
        db.refresh(ver_finding)

        EvidenceService.record_evidence(
            db=db,
            certification_id=run.certification_id,
            check_id=ver_chk.check_id,
            finding_id=ver_finding.id,
            source_system=SourceSystemEnum.ACE,
            source_reference=f"version-audit://{context.application_id}/{context.application_version}",
            evidence_type="VERSION_CONSISTENCY_AUDIT",
            evidence_data={"is_consistent": consistency_report.is_consistent, "discrepancies": consistency_report.discrepancies},
            source_version=context.application_version,
        )

        # Stage 7: Evaluate Policy (PolicyEngine)
        evidence_records = EvidenceService.get_evidence_for_certification(db, run.certification_id)
        final_status = PolicyEngine.evaluate_certification(context, checks, findings, evidence=evidence_records)

        # Stage 8: Generate Remediation (RemediationService)
        remediation_report = RemediationService.generate_remediation_report(
            certification_id=run.certification_id,
            application_id=context.application_id,
            application_version=context.application_version,
            overall_status=final_status.value,
            findings=findings,
        )

        # Stage 9: Persist Audit Trail
        EvidenceService.record_audit_event(
            db=db,
            event_type="CERTIFICATION_EVALUATED",
            actor="policy_engine",
            event_data={
                "certification_id": run.certification_id,
                "status": final_status.value,
                "checks_count": len(checks),
                "findings_count": len(findings),
            },
            certification_id=run.certification_id,
        )

        EvidenceService.record_audit_event(
            db=db,
            event_type="REMEDIATION_GENERATED",
            actor="remediation_service",
            event_data={
                "certification_id": run.certification_id,
                "actionable_items_count": remediation_report.actionable_items_count,
            },
            certification_id=run.certification_id,
        )

        # Stage 10: Complete Certification
        run.status = final_status.value
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)

        EvidenceService.record_audit_event(
            db=db,
            event_type="CERTIFICATION_COMPLETED",
            actor="certification_worker",
            event_data={
                "certification_id": run.certification_id,
                "final_status": run.status,
                "completed_at": run.completed_at.isoformat(),
            },
            certification_id=run.certification_id,
        )

        logger.info(
            f"Certification pipeline completed: {run.certification_id} status={run.status}",
            extra={
                "event": "certification_completed",
                "certification_id": run.certification_id,
                "application_id": run.application_id,
                "version": run.application_version,
                "status": run.status,
            },
        )

        return run
