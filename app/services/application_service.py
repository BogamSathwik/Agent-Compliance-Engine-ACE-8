"""Application and Version management service."""

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.application import Application, ApplicationTypeEnum
from app.models.application_version import ApplicationVersion
from app.models.certification import CertificationRun
from app.schemas.application import ApplicationCreate
from app.schemas.application_version import ApplicationVersionCreate
from app.core.exceptions import (
    ApplicationAlreadyExistsError,
    ApplicationNotFoundError,
    ACEException,
)
from app.services.evidence_service import EvidenceService
from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("ace.application_service")


class ApplicationVersionAlreadyExistsError(ACEException):
    def __init__(self, application_id: str, version: str):
        super().__init__(
            message=f"Version '{version}' already exists for application '{application_id}'.",
            code="APPLICATION_VERSION_ALREADY_EXISTS",
            status_code=409,
            details={"application_id": application_id, "version": version},
        )


class ApplicationVersionNotFoundError(ACEException):
    def __init__(self, application_id: str, version: str):
        super().__init__(
            message=f"Version '{version}' not found for application '{application_id}'.",
            code="APPLICATION_VERSION_NOT_FOUND",
            status_code=404,
            details={"application_id": application_id, "version": version},
        )


class ApplicationService:
    """Manages registered applications and multiple versions in ACE."""

    @staticmethod
    def create_application(db: Session, app_in: ApplicationCreate) -> Application:
        """Register a new application and its initial version."""
        existing = (
            db.query(Application)
            .filter(Application.application_id == app_in.application_id)
            .first()
        )
        if existing:
            logger.warning(
                f"Application '{app_in.application_id}' already exists",
                extra={
                    "event": "application_creation_rejected_duplicate",
                    "application_id": app_in.application_id,
                },
            )
            raise ApplicationAlreadyExistsError(app_in.application_id)

        version = app_in.get_version()
        application = Application(
            application_id=app_in.application_id,
            name=app_in.name,
            description=app_in.description,
            application_type=(
                app_in.application_type.value
                if isinstance(app_in.application_type, ApplicationTypeEnum)
                else str(app_in.application_type)
            ),
            current_version=version,
            repository_url=app_in.repository_url,
        )

        db.add(application)
        db.flush()

        # Create initial ApplicationVersion record
        initial_version = ApplicationVersion(
            application_id=application.application_id,
            version=version,
            commit_hash=app_in.commit_hash,
            source_reference=app_in.repository_url,
        )
        db.add(initial_version)

        db.commit()
        db.refresh(application)

        EvidenceService.record_audit_event(
            db=db,
            event_type="application_registered",
            actor="api_client",
            event_data={
                "application_id": application.application_id,
                "name": application.name,
                "version": application.current_version,
                "type": application.application_type,
            },
        )

        logger.info(
            f"Application registered: {application.application_id} (initial version {version})",
            extra={
                "event": "application_registered",
                "application_id": application.application_id,
                "version": application.current_version,
            },
        )

        # Automatic certification on application registration / initial submission when commit or submission reference provided
        curr_settings = get_settings()
        has_submission_ref = bool(app_in.commit_hash or app_in.submission_id)
        if curr_settings.AUTO_CERTIFY_ON_SUBMISSION and has_submission_ref:
            try:
                from app.schemas.certification import CertificationCreate
                from app.services.certification_service import CertificationService
                from app.models.certification import TriggerTypeEnum

                cert_service = CertificationService()
                sub_id = app_in.submission_id or f"SUB-{application.application_id}-{version}"
                cert_in = CertificationCreate(
                    application_id=application.application_id,
                    version=version,
                    commit_hash=app_in.commit_hash,
                    submission_id=sub_id,
                    trigger_type=TriggerTypeEnum.AGENT_SUBMISSION,
                )
                auto_run = cert_service.create_certification_run(db, cert_in)
                logger.info(
                    f"Automatic certification triggered for {application.application_id} (run {auto_run.certification_id})",
                    extra={
                        "event": "auto_certification_triggered",
                        "application_id": application.application_id,
                        "certification_id": auto_run.certification_id,
                        "submission_id": sub_id,
                    },
                )
            except Exception as exc:
                logger.warning(
                    f"Automatic certification trigger skipped or failed: {exc}",
                    extra={
                        "event": "auto_certification_warning",
                        "application_id": application.application_id,
                        "error": str(exc),
                    },
                )

        return application

    @staticmethod
    def get_application(db: Session, application_id: str) -> Application:
        """Fetch application by application_id or raise 404."""
        app = (
            db.query(Application)
            .filter(Application.application_id == application_id)
            .first()
        )
        if not app:
            raise ApplicationNotFoundError(application_id)
        return app

    @staticmethod
    def list_applications(
        db: Session, skip: int = 0, limit: int = 50
    ) -> Tuple[List[Application], int]:
        """List registered applications with total count."""
        total = db.query(Application).count()
        apps = (
            db.query(Application)
            .order_by(Application.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return apps, total

    @staticmethod
    def create_application_version(
        db: Session, application_id: str, version_in: ApplicationVersionCreate
    ) -> ApplicationVersion:
        """Register a new version for an existing application."""
        app = ApplicationService.get_application(db, application_id)

        existing_ver = (
            db.query(ApplicationVersion)
            .filter(
                ApplicationVersion.application_id == application_id,
                ApplicationVersion.version == version_in.version,
            )
            .first()
        )
        if existing_ver:
            raise ApplicationVersionAlreadyExistsError(application_id, version_in.version)

        new_version = ApplicationVersion(
            application_id=application_id,
            version=version_in.version,
            commit_hash=version_in.commit_hash,
            source_reference=version_in.source_reference,
            submission_id=version_in.submission_id,
        )
        db.add(new_version)

        # Update current_version on application
        app.current_version = version_in.version
        db.commit()
        db.refresh(new_version)

        EvidenceService.record_audit_event(
            db=db,
            event_type="application_version_created",
            actor="api_client",
            event_data={
                "application_id": application_id,
                "version": new_version.version,
                "commit_hash": new_version.commit_hash,
                "submission_id": new_version.submission_id,
            },
        )

        # Automatic certification on version submission when commit or submission reference provided
        curr_settings = get_settings()
        has_ver_submission_ref = bool(new_version.commit_hash or new_version.submission_id or new_version.source_reference)
        if curr_settings.AUTO_CERTIFY_ON_SUBMISSION and has_ver_submission_ref:
            try:
                from app.schemas.certification import CertificationCreate
                from app.services.certification_service import CertificationService
                from app.models.certification import TriggerTypeEnum

                cert_service = CertificationService()
                sub_id = new_version.submission_id or f"SUB-{application_id}-{new_version.version}"
                cert_in = CertificationCreate(
                    application_id=application_id,
                    version=new_version.version,
                    commit_hash=new_version.commit_hash,
                    submission_id=sub_id,
                    trigger_type=TriggerTypeEnum.VERSION_UPDATE,
                )
                auto_run = cert_service.create_certification_run(db, cert_in)
                logger.info(
                    f"Automatic certification triggered for {application_id} v{new_version.version} (run {auto_run.certification_id})",
                    extra={
                        "event": "auto_certification_triggered",
                        "application_id": application_id,
                        "certification_id": auto_run.certification_id,
                        "submission_id": sub_id,
                    },
                )
            except Exception as exc:
                logger.warning(
                    f"Automatic certification trigger skipped or failed: {exc}",
                    extra={
                        "event": "auto_certification_warning",
                        "application_id": application_id,
                        "version": new_version.version,
                        "error": str(exc),
                    },
                )

        return new_version

    @staticmethod
    def get_application_version(
        db: Session, application_id: str, version: str
    ) -> ApplicationVersion:
        """Fetch a specific version for an application."""
        ApplicationService.get_application(db, application_id)
        ver = (
            db.query(ApplicationVersion)
            .filter(
                ApplicationVersion.application_id == application_id,
                ApplicationVersion.version == version,
            )
            .first()
        )
        if not ver:
            raise ApplicationVersionNotFoundError(application_id, version)
        return ver

    @staticmethod
    def list_application_versions(
        db: Session, application_id: str
    ) -> List[ApplicationVersion]:
        """Fetch all registered versions for an application."""
        ApplicationService.get_application(db, application_id)
        return (
            db.query(ApplicationVersion)
            .filter(ApplicationVersion.application_id == application_id)
            .order_by(ApplicationVersion.created_at.desc())
            .all()
        )

    @staticmethod
    def get_latest_certification_status(
        db: Session, application_id: str
    ) -> Optional[CertificationRun]:
        """Retrieve the latest certification run for the given application."""
        ApplicationService.get_application(db, application_id)
        latest_run = (
            db.query(CertificationRun)
            .filter(CertificationRun.application_id == application_id)
            .order_by(CertificationRun.created_at.desc(), CertificationRun.id.desc())
            .first()
        )
        return latest_run
