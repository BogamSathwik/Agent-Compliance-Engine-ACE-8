"""FastAPI router for managing and testing external MCP integrations."""

from typing import Any, Dict, List, Optional
import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.mcp.client import ExternalMCPClient

logger = get_logger("ace.integrations")
router = APIRouter(prefix="/api/v1/integrations", tags=["Integrations"])


class IntegrationConfigItem(BaseModel):
    id: str = Field(..., description="Unique identifier for the integration service")
    name: str = Field(..., description="Display name of the integration")
    description: str = Field(..., description="Description of the service capability")
    service_type: str = Field(..., description="Target category: RAG, RULE_ENGINE, QA, PUBLICATION, CUSTOM")
    mcp_url: Optional[str] = Field(None, description="MCP Endpoint URL (e.g. http://localhost:3000/mcp)")
    mcp_auth_token: Optional[str] = Field(None, description="Auth token or Bearer secret for MCP")
    base_url: Optional[str] = Field(None, description="REST fallback URL")
    api_key: Optional[str] = Field(None, description="REST API key")
    is_active: bool = Field(True, description="Whether integration is enabled")
    expected_tools: List[str] = Field(default_factory=list, description="Expected MCP tools exposed by this service")


class IntegrationUpdateRequest(BaseModel):
    mcp_url: Optional[str] = None
    mcp_auth_token: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class ProbeRequest(BaseModel):
    mcp_url: str = Field(..., description="Target MCP URL to probe")
    auth_token: Optional[str] = Field(None, description="Optional bearer token")
    timeout: float = Field(default=8.0, description="Probe timeout in seconds")


class ProbeResponse(BaseModel):
    status: str = Field(..., description="SUCCESS or FAILED")
    mcp_url: str
    latency_ms: float
    server_info: Optional[Dict[str, Any]] = None
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    error_message: Optional[str] = None


def _mask_secret(secret: Optional[str]) -> Optional[str]:
    if not secret:
        return None
    if len(secret) <= 8:
        return "********"
    return f"{secret[:4]}...{secret[-4:]}"


@router.get("", summary="Get all configured external integrations and MCP status")
def get_integrations() -> Dict[str, Any]:
    """Retrieve all current external MCP integration configurations."""
    settings = get_settings()

    integrations = [
        {
            "id": "watchtower",
            "name": "Agent WatchTower (9-Rule Engine)",
            "description": "Evaluates 9 mandatory agent governance and safety rules.",
            "service_type": "RULE_ENGINE",
            "mcp_url": settings.RULE_ENGINE_MCP_URL or "",
            "mcp_auth_token": _mask_secret(settings.RULE_ENGINE_MCP_AUTH_TOKEN),
            "base_url": settings.RULE_ENGINE_BASE_URL or "",
            "api_key": _mask_secret(settings.RULE_ENGINE_API_KEY),
            "is_configured": bool(settings.RULE_ENGINE_MCP_URL or settings.RULE_ENGINE_BASE_URL),
            "expected_tools": ["evaluate_agent_rules"],
        },
        {
            "id": "myblocks_rag",
            "name": "MyBlocks RAG (Document Verification)",
            "description": "Retrieves compliance evidence across all 17 mandatory document categories.",
            "service_type": "RAG",
            "mcp_url": settings.MYBLOCKS_RAG_MCP_URL or "",
            "mcp_auth_token": _mask_secret(settings.MYBLOCKS_RAG_MCP_AUTH_TOKEN),
            "base_url": settings.MYBLOCKS_RAG_BASE_URL or "",
            "api_key": _mask_secret(settings.MYBLOCKS_RAG_API_KEY),
            "is_configured": bool(settings.MYBLOCKS_RAG_MCP_URL or settings.MYBLOCKS_RAG_BASE_URL),
            "expected_tools": ["verify_document_categories"],
        },
        {
            "id": "myblocks_qa",
            "name": "MyBlocks QA (Test Suite)",
            "description": "Automated authoritative QA test suite (scheduled within 1-week post-upload window).",
            "service_type": "QA",
            "mcp_url": settings.MYBLOCKS_QA_MCP_URL or "",
            "mcp_auth_token": _mask_secret(settings.MYBLOCKS_QA_MCP_AUTH_TOKEN),
            "base_url": settings.MYBLOCKS_QA_BASE_URL or "",
            "api_key": _mask_secret(settings.MYBLOCKS_QA_API_KEY),
            "is_configured": bool(settings.MYBLOCKS_QA_MCP_URL or settings.MYBLOCKS_QA_BASE_URL),
            "expected_tools": ["get_application_qa_status"],
        },
        {
            "id": "agentgen_pro",
            "name": "AgentGen Pro (Publication Platform)",
            "description": "External target platform for agent publication and catalog registration.",
            "service_type": "PUBLICATION",
            "mcp_url": settings.AGENTGEN_MCP_URL or "",
            "mcp_auth_token": _mask_secret(settings.AGENTGEN_MCP_AUTH_TOKEN),
            "base_url": settings.AGENTGEN_BASE_URL or "",
            "api_key": _mask_secret(settings.AGENTGEN_API_KEY),
            "is_configured": bool(settings.AGENTGEN_MCP_URL or settings.AGENTGEN_BASE_URL),
            "expected_tools": ["publish_agent"],
        },
    ]

    return {
        "integrations": integrations,
        "ace_mcp_server": {
            "endpoint": "/api/v1/mcp",
            "full_url": "http://localhost:8000/api/v1/mcp",
            "protocol_version": "2024-11-05",
            "auth_required": bool(settings.MCP_AUTH_TOKEN),
            "exposed_tools_count": 11,
            "description": "Other applications (like AgentGen or WatchTower) can connect to this endpoint to trigger certification or fetch reports.",
        },
    }


@router.put("/{integration_id}", summary="Update an external MCP integration endpoint")
def update_integration(integration_id: str, payload: IntegrationUpdateRequest) -> Dict[str, Any]:
    """Dynamically update an integration's MCP endpoint and credentials."""
    settings = get_settings()

    if integration_id == "watchtower":
        if payload.mcp_url is not None:
            settings.RULE_ENGINE_MCP_URL = payload.mcp_url.strip() or None
        if payload.mcp_auth_token is not None:
            settings.RULE_ENGINE_MCP_AUTH_TOKEN = payload.mcp_auth_token.strip() or None
        if payload.base_url is not None:
            settings.RULE_ENGINE_BASE_URL = payload.base_url.strip() or None
        if payload.api_key is not None:
            settings.RULE_ENGINE_API_KEY = payload.api_key.strip() or None
    elif integration_id == "myblocks_rag":
        if payload.mcp_url is not None:
            settings.MYBLOCKS_RAG_MCP_URL = payload.mcp_url.strip() or None
        if payload.mcp_auth_token is not None:
            settings.MYBLOCKS_RAG_MCP_AUTH_TOKEN = payload.mcp_auth_token.strip() or None
        if payload.base_url is not None:
            settings.MYBLOCKS_RAG_BASE_URL = payload.base_url.strip() or None
        if payload.api_key is not None:
            settings.MYBLOCKS_RAG_API_KEY = payload.api_key.strip() or None
    elif integration_id == "myblocks_qa":
        if payload.mcp_url is not None:
            settings.MYBLOCKS_QA_MCP_URL = payload.mcp_url.strip() or None
        if payload.mcp_auth_token is not None:
            settings.MYBLOCKS_QA_MCP_AUTH_TOKEN = payload.mcp_auth_token.strip() or None
        if payload.base_url is not None:
            settings.MYBLOCKS_QA_BASE_URL = payload.base_url.strip() or None
        if payload.api_key is not None:
            settings.MYBLOCKS_QA_API_KEY = payload.api_key.strip() or None
    elif integration_id == "agentgen_pro":
        if payload.mcp_url is not None:
            settings.AGENTGEN_MCP_URL = payload.mcp_url.strip() or None
        if payload.mcp_auth_token is not None:
            settings.AGENTGEN_MCP_AUTH_TOKEN = payload.mcp_auth_token.strip() or None
        if payload.base_url is not None:
            settings.AGENTGEN_BASE_URL = payload.base_url.strip() or None
        if payload.api_key is not None:
            settings.AGENTGEN_API_KEY = payload.api_key.strip() or None
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown integration ID '{integration_id}'",
        )

    logger.info(
        f"Integration '{integration_id}' updated successfully",
        extra={"event": "integration_updated", "integration_id": integration_id},
    )

    return {
        "status": "success",
        "integration_id": integration_id,
        "message": f"Integration '{integration_id}' updated successfully.",
    }


@router.post("/probe", response_model=ProbeResponse, summary="Probe an MCP endpoint to test connectivity and tools")
def probe_mcp_endpoint(payload: ProbeRequest) -> ProbeResponse:
    """Test connectivity to any MCP server and list available tools via JSON-RPC 2.0 tools/list."""
    import time
    start = time.time()
    url = payload.mcp_url.strip().rstrip("/")
    post_url = url if url.endswith("/mcp") else f"{url}/mcp"

    headers = {
        "User-Agent": "ACE-MCPClient/0.1.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if payload.auth_token:
        headers["Authorization"] = f"Bearer {payload.auth_token.strip()}"

    jsonrpc_body = {
        "jsonrpc": "2.0",
        "id": "ace-probe-1",
        "method": "tools/list",
        "params": {},
    }

    try:
        with httpx.Client(headers=headers, timeout=payload.timeout, follow_redirects=True) as client:
            resp = client.post(post_url, json=jsonrpc_body)
            elapsed = (time.time() - start) * 1000.0

            if resp.status_code != 200:
                return ProbeResponse(
                    status="FAILED",
                    mcp_url=post_url,
                    latency_ms=round(elapsed, 1),
                    error_message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            if "error" in data:
                err = data["error"]
                return ProbeResponse(
                    status="FAILED",
                    mcp_url=post_url,
                    latency_ms=round(elapsed, 1),
                    error_message=f"MCP Error ({err.get('code')}): {err.get('message')}",
                )

            tools: List[Dict[str, Any]] = []
            res_payload = data.get("result", {})
            if isinstance(res_payload, dict) and "tools" in res_payload:
                tools = res_payload.get("tools", [])
            elif isinstance(res_payload, list):
                tools = res_payload

            return ProbeResponse(
                status="SUCCESS",
                mcp_url=post_url,
                latency_ms=round(elapsed, 1),
                tools=tools,
            )

    except httpx.ConnectError:
        elapsed = (time.time() - start) * 1000.0
        return ProbeResponse(
            status="FAILED",
            mcp_url=post_url,
            latency_ms=round(elapsed, 1),
            error_message="Connection refused: MCP server is unreachable or offline at this address.",
        )
    except httpx.TimeoutException:
        elapsed = (time.time() - start) * 1000.0
        return ProbeResponse(
            status="FAILED",
            mcp_url=post_url,
            latency_ms=round(elapsed, 1),
            error_message=f"Request timed out after {payload.timeout} seconds.",
        )
    except Exception as exc:
        elapsed = (time.time() - start) * 1000.0
        return ProbeResponse(
            status="FAILED",
            mcp_url=post_url,
            latency_ms=round(elapsed, 1),
            error_message=str(exc),
        )
