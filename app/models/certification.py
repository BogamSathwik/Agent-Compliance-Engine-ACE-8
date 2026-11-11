"""SQLAlchemy model for Certification Runs."""

import enum
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class CertificationStatusEnum(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    NOT_READY = "NOT_READY"
    ERROR = "ERROR"


class TriggerTypeEnum(str, enum.Enum):
    MANUAL = "MANUAL"
    AGENT_SUBMISSION = "AGENT_SUBMISSION"
    VERSION_UPDATE = "VERSION_UPDATE"
    WEBHOOK = "WEBHOOK"
    RE_CERTIFICATION = "RE_CERTIFICATION"
    POLICY_CHANGE = "POLICY_CHANGE"


class CertificationRun(Base):
    __tablename__ = "certification_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    certification_id = Column(String(64), unique=True, nullable=False, index=True)
    application_id = Column(
        String(64),
        ForeignKey("applications.application_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_version_id = Column(
        Integer,
        ForeignKey("application_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    application_version = Column(String(64), nullable=False)
    commit_hash = Column(String(128), nullable=True)
    submission_id = Column(String(64), nullable=True, index=True)
    status = Column(
        String(64),
        nullable=False,
        default=CertificationStatusEnum.QUEUED.value,
        index=True,
    )
    trigger_type = Column(
        String(64),
        nullable=False,
        default=TriggerTypeEnum.MANUAL.value,
    )
    policy_version = Column(
        String(64),
        nullable=False,
        default="v1.0",
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    application = relationship("Application", back_populates="certification_runs")
    application_version_rel = relationship("ApplicationVersion", back_populates="certification_runs")
    checks = relationship(
        "CertificationCheck",
        back_populates="certification_run",
        cascade="all, delete-orphan",
        order_by="CertificationCheck.id",
    )
    findings = relationship(
        "CertificationFinding",
        back_populates="certification_run",
        cascade="all, delete-orphan",
        order_by="CertificationFinding.id",
    )
    evidence_records = relationship(
        "Evidence",
        back_populates="certification_run",
        cascade="all, delete-orphan",
        order_by="Evidence.id",
    )
    integration_runs = relationship(
        "IntegrationRun",
        back_populates="certification_run",
        cascade="all, delete-orphan",
        order_by="IntegrationRun.id",
    )
