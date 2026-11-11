"""SQLAlchemy model for Certification Findings."""

import enum
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship, foreign
from app.core.database import Base


class FindingCategoryEnum(str, enum.Enum):
    DOCUMENT = "DOCUMENT"
    QA = "QA"
    RULE = "RULE"
    SYSTEM = "SYSTEM"
    VERSION = "VERSION"
    INTEGRATION = "INTEGRATION"


class FindingStatusEnum(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_VERIFIED = "NOT_VERIFIED"
    PARTIAL = "PARTIAL"


class FindingSeverityEnum(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class RemediationStatusEnum(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class CertificationFinding(Base):
    __tablename__ = "certification_findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    certification_id = Column(
        String(64),
        ForeignKey("certification_runs.certification_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    check_id = Column(String(64), nullable=True, index=True)
    requirement_id = Column(String(64), nullable=True, index=True)
    finding_code = Column(String(64), nullable=True, index=True)
    category = Column(String(64), nullable=False, index=True)
    status = Column(String(64), nullable=False, default=FindingStatusEnum.NOT_VERIFIED.value)
    remediation_status = Column(
        String(32),
        nullable=False,
        default=RemediationStatusEnum.OPEN.value,
        index=True,
    )
    severity = Column(String(32), nullable=False, default=FindingSeverityEnum.MEDIUM.value)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    remediation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    certification_run = relationship("CertificationRun", back_populates="findings")
    check_rel = relationship(
        "CertificationCheck",
        primaryjoin="foreign(CertificationFinding.check_id) == CertificationCheck.check_id",
        back_populates="findings",
    )
    requirement_rel = relationship(
        "Requirement",
        primaryjoin="foreign(CertificationFinding.requirement_id) == Requirement.requirement_id",
        back_populates="findings",
    )
    evidence_records = relationship(
        "Evidence",
        back_populates="finding",
        order_by="Evidence.id",
    )
