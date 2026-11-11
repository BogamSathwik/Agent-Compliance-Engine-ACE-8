"""AgentGen Pro Publication Integration Client implementing PublicationClientProtocol.

Implements the safe integration boundary for AgentGen Pro publication.
Supports authenticated MCP invocation first, with authenticated HTTP REST fallback.
Never simulates successful publication when live credentials/endpoints are unavailable.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.mcp.client import ExternalMCPClient

logger = get_logger("ace.publication_client")


@dataclass
class ExternalPublicationResult:
    """Result of external publication request or verification from AgentGen Pro."""
    status: str  # "PUBLISHED", "FAILED", "UNKNOWN", "REQUESTED", "CONFIG_MISSING"
    external_publication_id: Optional[str] = None
    is_timeout: bool = False
    is_ambiguous: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    confirmation_details: Dict[str, Any] = field(default_factory=dict)
    raw_response: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PublicationClientProtocol(Protocol):
    """Protocol for AgentGen Pro publication client implementations."""

    def request_publication(
        self,
        application_id: str,
        version: str,
        certification_id: str,
        submission_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ExternalPublicationResult:
        """Request publication of an eligible certified application version."""
        ...

    def check_publication_status(
        self,
        application_id: str,
        version: str,
        external_publication_id: Optional[str] = None,
    ) -> ExternalPublicationResult:
        """Check the external publication status with AgentGen Pro."""
        ...


class AgentGenPublicationClient:
    """Production client for AgentGen Pro publication workflow."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        mcp_url: Optional[str] = None,
        mcp_auth_token: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        mcp_client: Optional[ExternalMCPClient] = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.AGENTGEN_BASE_URL or "").rstrip("/")
        self.api_key = api_key if api_key is not None else settings.AGENTGEN_API_KEY
        self.timeout = timeout if timeout is not None else settings.AGENTGEN_TIMEOUT
        self.mcp_url = mcp_url or settings.AGENTGEN_MCP_URL
        self.mcp_auth_token = mcp_auth_token or settings.AGENTGEN_MCP_AUTH_TOKEN
        self.mcp_client = mcp_client or (
            ExternalMCPClient(
                base_url=self.mcp_url,
                auth_token=self.mcp_auth_token,
                timeout=self.timeout,
                http_client=http_client,
            )
            if self.mcp_url
            else None
        )
        self._custom_client = http_client

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client
        headers = {
            "User-Agent": "ACE-ComplianceEngine/0.1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
            follow_redirects=True,
        )

    def request_publication(
        self,
        application_id: str,
        version: str,
        certification_id: str,
        submission_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ExternalPublicationResult:
        """Submit publication request to AgentGen Pro via MCP or authenticated REST."""
        # 1. MCP Invocation if configured
        if self.mcp_client and self.mcp_url:
            try:
                logger.info(
                    f"Submitting publication request via MCP to {self.mcp_url}",
                    extra={
                        "event": "agentgen_mcp_publish_request",
                        "application_id": application_id,
                        "version": version,
                        "certification_id": certification_id,
                    },
                )
                call_res = self.mcp_client.call_tool(
                    server_url=self.mcp_url,
                    tool_name="publish_agent",
                    arguments={
                        "application_id": application_id,
                        "version": version,
                        "certification_id": certification_id,
                        "submission_id": submission_id,
                        "notes": notes,
                    },
                )
                if call_res.get("isError"):
                    return ExternalPublicationResult(
                        status="FAILED",
                        error_code="AGENTGEN_MCP_ERROR",
                        error_message=str(call_res.get("content", "MCP tool reported failure")),
                        raw_response=call_res,
                    )
                content = call_res.get("content") or {}
                if isinstance(content, list) and content:
                    content = content[0].get("text", {}) if isinstance(content[0], dict) else content[0]
                if isinstance(content, str):
                    import json
                    try:
                        content = json.loads(content)
                    except Exception:
                        content = {"raw": content}

                ext_id = content.get("publication_id") or content.get("external_publication_id")
                ext_status = content.get("status", "").upper()
                if ext_status == "PUBLISHED":
                    return ExternalPublicationResult(
                        status="PUBLISHED",
                        external_publication_id=ext_id,
                        confirmation_details=content,
                        raw_response=call_res,
                    )
                return ExternalPublicationResult(
                    status="REQUESTED",
                    external_publication_id=ext_id,
                    confirmation_details=content,
                    raw_response=call_res,
                )
            except httpx.TimeoutException:
                return ExternalPublicationResult(
                    status="UNKNOWN",
                    is_timeout=True,
                    error_code="TIMEOUT",
                    error_message="AgentGen Pro MCP publication request timed out",
                )
            except Exception as exc:
                logger.warning(f"AgentGen Pro MCP call failed: {exc}")
                return ExternalPublicationResult(
                    status="FAILED",
                    error_code="MCP_CALL_FAILED",
                    error_message=str(exc),
                )

        # 2. REST Fallback if configured
        if self.base_url:
            try:
                client = self._get_client()
                logger.info(
                    f"Submitting publication request via REST to {self.base_url}/api/v1/publish",
                    extra={
                        "event": "agentgen_rest_publish_request",
                        "application_id": application_id,
                        "version": version,
                        "certification_id": certification_id,
                    },
                )
                resp = client.post(
                    f"{self.base_url}/api/v1/publish",
                    json={
                        "application_id": application_id,
                        "version": version,
                        "certification_id": certification_id,
                        "submission_id": submission_id,
                        "notes": notes,
                    },
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    ext_id = data.get("publication_id") or data.get("external_publication_id")
                    ext_status = data.get("status", "").upper()
                    if ext_status == "PUBLISHED":
                        return ExternalPublicationResult(
                            status="PUBLISHED",
                            external_publication_id=ext_id,
                            confirmation_details=data,
                            raw_response=data,
                        )
                    return ExternalPublicationResult(
                        status="REQUESTED",
                        external_publication_id=ext_id,
                        confirmation_details=data,
                        raw_response=data,
                    )
                else:
                    return ExternalPublicationResult(
                        status="FAILED",
                        error_code=f"HTTP_{resp.status_code}",
                        error_message=resp.text[:300],
                        raw_response={"status_code": resp.status_code, "text": resp.text},
                    )
            except httpx.TimeoutException:
                return ExternalPublicationResult(
                    status="UNKNOWN",
                    is_timeout=True,
                    error_code="TIMEOUT",
                    error_message="AgentGen Pro REST publication request timed out",
                )
            except Exception as exc:
                logger.warning(f"AgentGen Pro REST call failed: {exc}")
                return ExternalPublicationResult(
                    status="FAILED",
                    error_code="REST_CALL_FAILED",
                    error_message=str(exc),
                )

        # 3. Neither MCP nor REST is configured: safe integration boundary
        logger.info("AgentGen Pro publication endpoint is not configured in environment.")
        return ExternalPublicationResult(
            status="CONFIG_MISSING",
            error_code="AGENTGEN_NOT_CONFIGURED",
            error_message=(
                "AgentGen Pro publication integration is not configured. "
                "Configure AGENTGEN_MCP_URL or AGENTGEN_BASE_URL with appropriate credentials."
            ),
        )

    def check_publication_status(
        self,
        application_id: str,
        version: str,
        external_publication_id: Optional[str] = None,
    ) -> ExternalPublicationResult:
        """Check external publication status with AgentGen Pro."""
        if not self.mcp_url and not self.base_url:
            return ExternalPublicationResult(
                status="CONFIG_MISSING",
                error_code="AGENTGEN_NOT_CONFIGURED",
                error_message="AgentGen Pro publication endpoint is not configured.",
            )

        # MCP check
        if self.mcp_client and self.mcp_url:
            try:
                call_res = self.mcp_client.call_tool(
                    server_url=self.mcp_url,
                    tool_name="get_publication_status",
                    arguments={
                        "application_id": application_id,
                        "version": version,
                        "external_publication_id": external_publication_id,
                    },
                )
                if not call_res.get("isError"):
                    content = call_res.get("content") or {}
                    if isinstance(content, list) and content:
                        content = content[0].get("text", {}) if isinstance(content[0], dict) else content[0]
                    if isinstance(content, str):
                        import json
                        try:
                            content = json.loads(content)
                        except Exception:
                            content = {"status": content}
                    st = content.get("status", "").upper()
                    if st == "PUBLISHED":
                        return ExternalPublicationResult(
                            status="PUBLISHED",
                            external_publication_id=external_publication_id or content.get("publication_id"),
                            confirmation_details=content,
                            raw_response=call_res,
                        )
                    elif st in ("FAILED", "REJECTED"):
                        return ExternalPublicationResult(
                            status="FAILED",
                            error_code="EXTERNAL_REJECTED",
                            error_message=content.get("error_message", "External publication rejected"),
                            raw_response=call_res,
                        )
            except Exception as exc:
                logger.warning(f"AgentGen MCP status check failed: {exc}")

        # REST check
        if self.base_url:
            try:
                client = self._get_client()
                url = f"{self.base_url}/api/v1/publish/{external_publication_id}" if external_publication_id else f"{self.base_url}/api/v1/publish/status"
                resp = client.get(url, params={"application_id": application_id, "version": version})
                if resp.status_code == 200:
                    data = resp.json()
                    st = data.get("status", "").upper()
                    if st == "PUBLISHED":
                        return ExternalPublicationResult(
                            status="PUBLISHED",
                            external_publication_id=external_publication_id or data.get("publication_id"),
                            confirmation_details=data,
                            raw_response=data,
                        )
                    elif st in ("FAILED", "REJECTED"):
                        return ExternalPublicationResult(
                            status="FAILED",
                            error_code="EXTERNAL_REJECTED",
                            error_message=data.get("error_message", "External publication rejected"),
                            raw_response=data,
                        )
            except Exception as exc:
                logger.warning(f"AgentGen REST status check failed: {exc}")

        return ExternalPublicationResult(
            status="UNKNOWN",
            is_ambiguous=True,
            error_code="STATUS_UNKNOWN",
            error_message="Could not authoritatively verify publication status with AgentGen Pro",
        )
