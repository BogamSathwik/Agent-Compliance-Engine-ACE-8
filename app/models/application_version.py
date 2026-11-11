"""SQLAlchemy model for Application Versions."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, Index, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class ApplicationVersion(Base):
    __tablename__ = "application_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(
        String(64),
        ForeignKey("applications.application_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(String(64), nullable=False, index=True)
    commit_hash = Column(String(128), nullable=True)
    source_reference = Column(String(255), nullable=True)
    submission_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("application_id", "version", name="uq_application_versions_app_version"),
        Index("ix_application_versions_app_commit", "application_id", "commit_hash"),
    )

    application = relationship("Application", back_populates="versions")
    certification_runs = relationship(
        "CertificationRun",
        back_populates="application_version_rel",
        cascade="all, delete-orphan",
        order_by="desc(CertificationRun.created_at)",
    )
