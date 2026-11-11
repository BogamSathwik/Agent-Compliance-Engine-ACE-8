"""SQLAlchemy model for AgentGen Pro Publications."""

import enum
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class PublicationStatusEnum(str, enum.Enum):
    CERTIFIED = "CERTIFIED"
    PUBLICATION_REQUESTED = "PUBLICATION_REQUESTED"
    PUBLISHED = "PUBLISHED"
    PUBLICATION_FAILED = "PUBLICATION_FAILED"
    PUBLICATION_STATUS_UNKNOWN = "PUBLICATION_STATUS_UNKNOWN"


class PublicationRecord(Base):
    __tablename__ = "publication_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    publication_id = Column(String(64), unique=True, nullable=False, index=True)
    application_id = Column(
        String(64),
        ForeignKey("applications.application_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_version = Column(String(64), nullable=False, index=True)
    application_version_id = Column(
        Integer,
        ForeignKey("application_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    certification_id = Column(
        String(64),
        ForeignKey("certification_runs.certification_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submission_id = Column(String(64), nullable=True, index=True)
    status = Column(
        String(64),
        nullable=False,
        default=PublicationStatusEnum.CERTIFIED.value,
        index=True,
    )
    external_publication_id = Column(String(128), nullable=True, index=True)
    external_status = Column(String(64), nullable=True)
    external_confirmation = Column(JSON, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    requested_by = Column(String(64), default="operator", nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    application = relationship("Application", back_populates="publications")
    certification_run = relationship("CertificationRun")
