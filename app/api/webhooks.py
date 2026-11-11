from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.services.publication_service import PublicationService

logger = get_logger("ace.webhooks")
router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


class WebhookPayload(BaseModel):
    event_type: str
    source: str
    payload: dict


@router.post(
    "/agentgen",
    status_code=status.HTTP_200_OK,
    summary="AgentGen Pro publication notification webhook",
)
def handle_agentgen_webhook(data: WebhookPayload, db: Session = Depends(get_db)):
    """Receive authoritative publication status events from AgentGen Pro."""
    logger.info(
        f"Received AgentGen webhook: event={data.event_type}, source={data.source}",
        extra={"event": "agentgen_webhook_received", "event_type": data.event_type},
    )

    if data.event_type in ("PUBLICATION_CONFIRMED", "AGENT_PUBLISHED", "PUBLISHED", "PUBLICATION_FAILED"):
        pub_id = data.payload.get("publication_id")
        ext_pub_id = data.payload.get("external_publication_id")
        ext_status = "PUBLISHED" if data.event_type in ("PUBLICATION_CONFIRMED", "AGENT_PUBLISHED", "PUBLISHED") else "FAILED"
        if data.payload.get("status"):
            ext_status = str(data.payload.get("status")).upper()

        if pub_id or ext_pub_id:
            try:
                service = PublicationService()
                rec = service.confirm_external_publication(
                    db=db,
                    publication_id=pub_id or "",
                    external_publication_id=ext_pub_id or "",
                    status=ext_status,
                    confirmation_details=data.payload,
                    error_message=data.payload.get("error_message"),
                    actor="agentgen_webhook",
                )
                return {
                    "status": "processed",
                    "event_type": data.event_type,
                    "publication_id": rec.publication_id,
                    "publication_status": rec.status,
                }
            except Exception as exc:
                logger.warning(f"Error processing AgentGen publication webhook: {exc}")

    return {
        "status": "received",
        "event_type": data.event_type,
        "message": "Webhook processed successfully",
    }

