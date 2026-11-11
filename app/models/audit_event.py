"""SQLAlchemy model for Audit Events."""

from sqlalchemy import JSON, Column, DateTime, Integer, String, func
from app.core.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    certification_id = Column(String(64), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    actor = Column(String(128), nullable=False)
    event_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
