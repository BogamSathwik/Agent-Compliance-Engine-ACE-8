"""SQLAlchemy model for External Integration Runs."""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class IntegrationRun(Base):
    __tablename__ = "integration_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    certification_id = Column(
        String(64),
        ForeignKey("certification_runs.certification_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_run_id = Column(String(64), unique=True, nullable=False, index=True)
    source_system = Column(String(64), nullable=False, index=True)
    operation = Column(String(128), nullable=False)
    status = Column(String(64), nullable=False, index=True)
    external_application_id = Column(String(64), nullable=True)
    external_version = Column(String(64), nullable=True)
    external_run_id = Column(String(128), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    response_metadata = Column(JSON, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    certification_run = relationship("CertificationRun", back_populates="integration_runs")
