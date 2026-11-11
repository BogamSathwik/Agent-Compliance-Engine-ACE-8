"""SQLAlchemy model for Certification Checks."""

import enum
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship, foreign
from app.core.database import Base


class CheckTypeEnum(str, enum.Enum):
    DOCUMENT = "DOCUMENT"
    QA = "QA"
    RULE = "RULE"
    AGENT_RULES = "AGENT_RULES"
    VERSION = "VERSION"
    SYSTEM = "SYSTEM"
    INTEGRATION = "INTEGRATION"


class CheckStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    NOT_VERIFIED = "NOT_VERIFIED"
    ERROR = "ERROR"


class CertificationCheck(Base):
    __tablename__ = "certification_checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    certification_id = Column(
        String(64),
        ForeignKey("certification_runs.certification_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    check_id = Column(String(64), nullable=False, index=True)
    check_type = Column(String(64), nullable=False, index=True)
    check_name = Column(String(255), nullable=False)
    status = Column(String(64), nullable=False, default=CheckStatusEnum.PENDING.value)
    source_system = Column(String(64), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    certification_run = relationship("CertificationRun", back_populates="checks")
    findings = relationship(
        "CertificationFinding",
        primaryjoin="CertificationCheck.check_id == foreign(CertificationFinding.check_id)",
        back_populates="check_rel",
        cascade="all, delete-orphan",
        order_by="CertificationFinding.id",
    )
    evidence_records = relationship(
        "Evidence",
        primaryjoin="CertificationCheck.check_id == foreign(Evidence.check_id)",
        back_populates="check_rel",
        order_by="Evidence.id",
    )
