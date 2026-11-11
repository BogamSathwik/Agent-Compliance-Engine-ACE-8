"""SQLAlchemy model for Evidence."""

import enum
from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship, foreign
from app.core.database import Base


class SourceSystemEnum(str, enum.Enum):
    MYBLOCKS_RAG = "MYBLOCKS_RAG"
    MYBLOCKS_QA = "MYBLOCKS_QA"
    RULE_ENGINE = "RULE_ENGINE"
    AGENTGEN = "AGENTGEN"
    ACE = "ACE"


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    certification_id = Column(
        String(64),
        ForeignKey("certification_runs.certification_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    check_id = Column(String(64), nullable=True, index=True)
    finding_id = Column(
        Integer,
        ForeignKey("certification_findings.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_system = Column(String(64), nullable=False)
    source_reference = Column(String(255), nullable=True)
    evidence_type = Column(String(64), nullable=False)
    evidence_data = Column(JSON, nullable=False)
    source_version = Column(String(64), nullable=True)
    source_run_id = Column(String(128), nullable=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    hash = Column(String(128), nullable=True)
    confidence = Column(Float, nullable=True)
    collected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    certification_run = relationship("CertificationRun", back_populates="evidence_records")
    finding = relationship("CertificationFinding", back_populates="evidence_records")
    check_rel = relationship(
        "CertificationCheck",
        primaryjoin="foreign(Evidence.check_id) == CertificationCheck.check_id",
        back_populates="evidence_records",
    )
