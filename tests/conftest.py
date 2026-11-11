"""Pytest fixtures and test environment configuration."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.database import Base, get_db
import app.models  # Ensure all models are registered on Base
from app.main import app
from app.workers.celery_app import celery_app
import app.workers.certification_worker as worker_module

# Test SQLite in-memory database with StaticPool (retains tables across sessions)
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def get_test_settings() -> Settings:
    return Settings(
        APP_NAME="ACE-Test",
        ENVIRONMENT="test",
        DEBUG=True,
        DATABASE_URL=SQLALCHEMY_TEST_DATABASE_URL,
        TESTING=True,
        EXECUTION_MODE="async",
        CELERY_ALWAYS_EAGER=False,
        AUTO_CERTIFY_ON_SUBMISSION=False,
        DEFER_QA_UNTIL_POST_UPLOAD=False,
    )


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configure Celery eager mode and override settings for testing."""
    import os
    os.environ["TESTING"] = "true"
    os.environ["EXECUTION_MODE"] = "async"
    os.environ["CELERY_ALWAYS_EAGER"] = "false"
    os.environ["AUTO_CERTIFY_ON_SUBMISSION"] = "false"
    os.environ["DEFER_QA_UNTIL_POST_UPLOAD"] = "false"
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = get_test_settings
    celery_app.conf.update(
        task_always_eager=False,  # We mock delay explicitly
    )


@pytest.fixture(autouse=True)
def mock_celery_delay(monkeypatch):
    """Globally mock Celery delay in all tests to avoid network calls to Redis."""
    queued = []

    def mock_delay(certification_id):
        queued.append(certification_id)
        return True

    monkeypatch.setattr(worker_module.run_certification_task, "delay", mock_delay)
    return queued


@pytest.fixture(scope="function")
def db_session():
    """Create fresh isolated tables for each test and provide a session."""
    from app.services.requirement_service import RequirementService
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    RequirementService.seed_mandatory_requirements(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session, mock_celery_delay):
    """Test client with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        test_client.queued_tasks = mock_celery_delay
        yield test_client

    app.dependency_overrides.pop(get_db, None)
