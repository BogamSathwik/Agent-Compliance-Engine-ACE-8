"""SQLAlchemy model for Applications."""

import enum
from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class ApplicationTypeEnum(str, enum.Enum):
    AI_AGENT = "AI_AGENT"
    WEB_APP = "WEB_APP"
    OTHER = "OTHER"


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    application_type = Column(String(64), nullable=False, default=ApplicationTypeEnum.AI_AGENT.value)
    current_version = Column(String(64), nullable=False)
    repository_url = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)

    certification_runs = relationship(
        "CertificationRun",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(CertificationRun.created_at)",
    )
    versions = relationship(
        "ApplicationVersion",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(ApplicationVersion.created_at)",
    )
    publications = relationship(
        "PublicationRecord",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(PublicationRecord.created_at)",
    )


