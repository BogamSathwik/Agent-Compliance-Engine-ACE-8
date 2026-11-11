"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ACE configuration settings loaded from environment variables."""

    # Application settings
    APP_NAME: str = "ACE-AgentComplianceEngine"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "default-insecure-secret-key-change-in-production"

    # MySQL Database configuration
    DATABASE_URL: str = "mysql+pymysql://ace_user:ace_password@localhost:3306/ace_db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_PRE_PING: bool = True

    # Redis / Celery configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    CELERY_ALWAYS_EAGER: bool = False  # Runs Celery tasks in-process synchronously when broker is not used
    EXECUTION_MODE: str = "async"  # "async" for Celery background worker, "sync" for deterministic in-process
    AUTO_CERTIFY_ON_SUBMISSION: bool = True  # Automatically trigger certification on application / version submission

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" or "text"

    # MyBlocks RAG configuration
    MYBLOCKS_RAG_BASE_URL: str = "https://myblocks.in/myblock_private"
    MYBLOCKS_RAG_API_KEY: Optional[str] = None
    MYBLOCKS_RAG_TIMEOUT: float = 10.0
    MYBLOCKS_RAG_MCP_URL: Optional[str] = None
    MYBLOCKS_RAG_MCP_AUTH_TOKEN: Optional[str] = None
    MYBLOCKS_RAG_MCP_TIMEOUT: float = 10.0

    # MyBlocks QA configuration (Phase 4)
    MYBLOCKS_QA_BASE_URL: str = "https://myblocks.in/qa_app"
    MYBLOCKS_QA_API_KEY: Optional[str] = None
    MYBLOCKS_QA_TIMEOUT: float = 10.0
    MYBLOCKS_QA_MCP_URL: Optional[str] = None
    MYBLOCKS_QA_MCP_AUTH_TOKEN: Optional[str] = None
    MYBLOCKS_QA_MCP_TIMEOUT: float = 10.0
    DEFER_QA_UNTIL_POST_UPLOAD: bool = True
    QA_SCHEDULE_WINDOW_DAYS: int = 7

    # 9-Rule Agent Evaluation configuration (Phase 5)
    RULE_ENGINE_BASE_URL: Optional[str] = None
    RULE_ENGINE_API_KEY: Optional[str] = None
    RULE_ENGINE_TIMEOUT: float = 10.0
    RULE_ENGINE_MCP_URL: Optional[str] = None
    RULE_ENGINE_MCP_AUTH_TOKEN: Optional[str] = None
    RULE_ENGINE_MCP_TIMEOUT: float = 15.0

    # AgentGen Pro Publication Integration (Phase 9)
    AGENTGEN_BASE_URL: Optional[str] = None
    AGENTGEN_API_KEY: Optional[str] = None
    AGENTGEN_TIMEOUT: float = 10.0
    AGENTGEN_MCP_URL: Optional[str] = None
    AGENTGEN_MCP_AUTH_TOKEN: Optional[str] = None
    AGENTGEN_MCP_TIMEOUT: float = 15.0

    # MCP Server settings (ACE as Provider)
    MCP_SERVER_ENABLED: bool = True
    MCP_AUTH_TOKEN: Optional[str] = None

    # Testing flag
    TESTING: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
