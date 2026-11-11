"""Structured logging configuration for ACE."""

import datetime
import json
import logging
import sys
from typing import Any, Dict

SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "credentials",
    "secret_key",
}


def sanitize_data(data: Any) -> Any:
    """Recursively mask sensitive keys in log payloads."""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if any(sens in str(key).lower() for sens in SENSITIVE_KEYS):
                sanitized[key] = "********"
            else:
                sanitized[key] = sanitize_data(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured log outputs."""

    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include certification operation structured fields if present
        for field in [
            "event",
            "certification_id",
            "application_id",
            "application_version",
            "version",
            "commit_hash",
            "status",
        ]:
            if hasattr(record, field):
                log_record[field] = getattr(record, field)

        # Include extra payload if provided
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_record["data"] = sanitize_data(record.extra_data)

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure root logger with structured JSON or text formatting."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to prevent duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if log_format.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
            )
        )

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)
