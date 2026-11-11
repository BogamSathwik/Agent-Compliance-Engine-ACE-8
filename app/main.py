"""ACE - Agent Compliance Engine FastAPI Application Entrypoint."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.core.exceptions import ACEException
from app.api.health import router as health_router
from app.api.applications import router as applications_router
from app.api.certifications import router as certifications_router
from app.api.publications import router as publications_router
from app.api.webhooks import router as webhooks_router
from app.api.mcp import router as mcp_router
from app.api.integrations import router as integrations_router

settings = get_settings()
setup_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
logger = get_logger("ace.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle handler."""
    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]",
        extra={"event": "application_startup", "environment": settings.ENVIRONMENT},
    )
    # Seed mandatory requirements if database is available
    try:
        from app.core.database import SessionLocal
        from app.services.requirement_service import RequirementService
        db = SessionLocal()
        try:
            RequirementService.seed_mandatory_requirements(db)
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Requirement seeding skipped on startup: {exc}")

    yield
    logger.info(
        f"Shutting down {settings.APP_NAME}",
        extra={"event": "application_shutdown"},
    )


from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(
    title="ACE — Agent Compliance Engine",
    description=(
        "Autonomous certification platform for AgentGen Pro. "
        "Evaluates AI agents and web applications across documentation (MyBlocks RAG), "
        "QA test suites (MyBlocks QA), and 9-rule agent governance policies before publication."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================================
# Global Exception Handlers (Never leak stack traces or internal secrets)
# =========================================================================

@app.exception_handler(ACEException)
async def ace_exception_handler(request: Request, exc: ACEException):
    logger.warning(
        f"ACE domain exception: {exc.code} - {exc.message}",
        extra={
            "event": "domain_exception",
            "error_code": exc.code,
            "status_code": exc.status_code,
            "path": request.url.path,
            "extra_data": exc.details,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        errors.append({
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "type": err.get("type"),
        })

    logger.warning(
        f"Request validation failure on {request.url.path}",
        extra={
            "event": "request_validation_failure",
            "path": request.url.path,
            "errors": errors,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Input validation failed. Please check the request fields.",
                "details": {"validation_errors": errors},
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled server error on {request.url.path}: {exc}",
        exc_info=True,
        extra={
            "event": "unhandled_internal_error",
            "path": request.url.path,
            "error": str(exc),
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal server error occurred.",
                "details": {},
            }
        },
    )


# =========================================================================
# Route Registrations
# =========================================================================

app.include_router(health_router)
app.include_router(health_router, prefix=settings.API_V1_STR)
app.include_router(applications_router)
app.include_router(certifications_router)
app.include_router(publications_router)
app.include_router(webhooks_router)
app.include_router(integrations_router)
app.include_router(mcp_router, prefix=settings.API_V1_STR)
app.include_router(mcp_router)

# =========================================================================
# Static Frontend Serving (Optional built UI)
# =========================================================================
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_dist):
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    async def serve_frontend_index():
        return FileResponse(os.path.join(frontend_dist, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
