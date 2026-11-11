"""Pydantic schemas for Audit Events."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    id: int
    certification_id: Optional[str] = None
    event_type: str
    actor: str
    event_data: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditTrailResponse(BaseModel):
    certification_id: str
    total_events: int
    events: List[AuditEventResponse]

    model_config = ConfigDict(from_attributes=True)
