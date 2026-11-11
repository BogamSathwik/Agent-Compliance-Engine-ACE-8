"""Health and readiness probe endpoints."""

from fastapi import APIRouter, status, Response
from app.core.config import get_settings
from app.core.database import check_db_connectivity

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Simple liveness probe."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@router.get("/health/ready")
def readiness_check(response: Response):
    """Readiness probe verifying MySQL database connectivity."""
    is_db_connected = check_db_connectivity()
    if is_db_connected:
        return {
            "status": "ready",
            "database": "connected",
        }
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "database": "disconnected",
            "message": "Database connectivity check failed",
        }
