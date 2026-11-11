"""Custom domain exceptions for ACE."""

from typing import Any, Dict, Optional


class ACEException(Exception):
    """Base exception for all ACE errors."""

    def __init__(
        self,
        message: str,
        code: str = "ACE_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class ApplicationNotFoundError(ACEException):
    def __init__(self, application_id: str):
        super().__init__(
            message=f"Application '{application_id}' was not found.",
            code="APPLICATION_NOT_FOUND",
            status_code=404,
            details={"application_id": application_id},
        )


class ApplicationAlreadyExistsError(ACEException):
    def __init__(self, application_id: str):
        super().__init__(
            message=f"Application with ID '{application_id}' already exists.",
            code="APPLICATION_ALREADY_EXISTS",
            status_code=409,
            details={"application_id": application_id},
        )


class CertificationNotFoundError(ACEException):
    def __init__(self, certification_id: str):
        super().__init__(
            message=f"Certification run '{certification_id}' was not found.",
            code="CERTIFICATION_NOT_FOUND",
            status_code=404,
            details={"certification_id": certification_id},
        )


class CertificationAlreadyRunningError(ACEException):
    def __init__(self, application_id: str, version: str):
        super().__init__(
            message=f"An active certification is already running for application '{application_id}' at version '{version}'.",
            code="CERTIFICATION_ALREADY_RUNNING",
            status_code=409,
            details={"application_id": application_id, "version": version},
        )


class InvalidVersionError(ACEException):
    def __init__(self, version: str, reason: str = "Invalid semantic version format"):
        super().__init__(
            message=f"Version '{version}' is invalid: {reason}",
            code="INVALID_VERSION",
            status_code=400,
            details={"version": version, "reason": reason},
        )


class DatabaseConnectionError(ACEException):
    def __init__(self, message: str = "Database connection unavailable"):
        super().__init__(
            message=message,
            code="DATABASE_CONNECTION_ERROR",
            status_code=503,
        )


class BackgroundJobError(ACEException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="BACKGROUND_JOB_ERROR",
            status_code=500,
            details=details,
        )


class PublicationEligibilityError(ACEException):
    def __init__(self, application_id: str, version: str, reason: str):
        super().__init__(
            message=f"Application '{application_id}' (v{version}) is not eligible for publication: {reason}",
            code="PUBLICATION_INELIGIBLE",
            status_code=400,
            details={"application_id": application_id, "version": version, "reason": reason},
        )


class PublicationAlreadyExistsError(ACEException):
    def __init__(self, application_id: str, version: str, publication_id: str):
        super().__init__(
            message=f"Application '{application_id}' (v{version}) is already published under publication '{publication_id}'.",
            code="ALREADY_PUBLISHED",
            status_code=409,
            details={"application_id": application_id, "version": version, "publication_id": publication_id},
        )


class PublicationNotFoundError(ACEException):
    def __init__(self, identifier: str):
        super().__init__(
            message=f"Publication record '{identifier}' was not found.",
            code="PUBLICATION_NOT_FOUND",
            status_code=404,
            details={"identifier": identifier},
        )

