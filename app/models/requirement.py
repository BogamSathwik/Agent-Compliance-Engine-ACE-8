"""SQLAlchemy model for Compliance Requirements."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import relationship, foreign
from app.core.database import Base


class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(String(64), unique=True, nullable=False, index=True)
    category = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    mandatory = Column(Boolean, nullable=False, default=True)
    active = Column(Boolean, nullable=False, default=True)
    policy_version = Column(String(64), nullable=False, default="v1.0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    findings = relationship(
        "CertificationFinding",
        primaryjoin="Requirement.requirement_id == foreign(CertificationFinding.requirement_id)",
        back_populates="requirement_rel",
    )
