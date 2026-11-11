"""Background worker for certification run execution."""

from app.workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.services.certification_service import CertificationService
from app.models.certification import CertificationStatusEnum, CertificationRun
from app.services.evidence_service import EvidenceService

logger = get_logger("ace.certification_worker")


@celery_app.task(name="run_certification_task", bind=True, max_retries=2)
def run_certification_task(self, certification_id: str) -> dict:
    """Execute background certification evaluation.

    Pipeline:
    1. Load certification run.
    2. Set status to RUNNING.
    3. Execute modular certification pipeline placeholder.
    4. Persist structured findings and collected evidence.
    5. Set final status deterministically (NOT_READY in Phase 1 pending external integrations).
    """
    logger.info(
        f"Celery worker received certification task: {certification_id}",
        extra={
            "event": "worker_task_received",
            "certification_id": certification_id,
        },
    )

    db = SessionLocal()
    service = CertificationService()
    try:
        run = service.execute_certification_pipeline(db, certification_id)
        return {
            "certification_id": run.certification_id,
            "status": run.status,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
    except Exception as exc:
        logger.error(
            f"Error executing certification {certification_id}: {exc}",
            exc_info=True,
            extra={
                "event": "worker_task_failed",
                "certification_id": certification_id,
                "error": str(exc),
            },
        )
        # Mark certification as ERROR
        try:
            failed_run = (
                db.query(CertificationRun)
                .filter(CertificationRun.certification_id == certification_id)
                .first()
            )
            if failed_run:
                failed_run.status = CertificationStatusEnum.ERROR.value
                db.commit()

                EvidenceService.record_audit_event(
                    db=db,
                    event_type="certification_failed_error",
                    actor="certification_worker",
                    event_data={
                        "certification_id": certification_id,
                        "error": str(exc),
                    },
                    certification_id=certification_id,
                )
        except Exception as inner_exc:
            logger.error(f"Failed to record failure state for {certification_id}: {inner_exc}")

        raise exc
    finally:
        db.close()
