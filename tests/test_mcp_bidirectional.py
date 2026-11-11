"""Bidirectional MCP smoke tests: ACE as Provider (Server) and Consumer (Client)."""

import json
import httpx
from app.mcp.server import ACEMCPServer
from app.mcp.client import ExternalMCPClient
from app.models.certification import CertificationStatusEnum
from app.models.finding import FindingStatusEnum
from app.services.application_service import ApplicationService
from app.schemas.application import ApplicationCreate
from app.integrations.contracts import MANDATORY_17_DOC_CATEGORIES


def test_mcp_server_exposes_required_tools(client):
    """Verify ACE MCP Server exposes the 6 required business capabilities."""
    tools = ACEMCPServer.list_tools()
    tool_names = {t["name"] for t in tools}

    assert "start_certification" in tool_names
    assert "get_certification_status" in tool_names
    assert "get_publication_status" in tool_names
    assert "get_certification_findings" in tool_names
    assert "get_certification_evidence" in tool_names
    assert "get_remediation" in tool_names

    # Check via HTTP discovery endpoint
    res = client.get("/api/v1/mcp")
    assert res.status_code == 200
    data = res.json()
    assert data["protocolVersion"] == "2024-11-05"
    assert "tools" in data["capabilities"]

    # Verify no dangerous generic tools exist
    forbidden = {"execute_sql", "execute_shell", "execute_python", "run_anything"}
    assert tool_names.isdisjoint(forbidden)


def test_mcp_server_invokes_certification_and_returns_status(client, db_session):
    """External caller (e.g. AgentGen Pro) uses MCP tools/call to queue and inspect certification."""
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-MCP-01", name="AgentGen MCP Agent", version="1.0.0"),
    )

    # 1. tools/call -> start_certification
    req = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "tools/call",
        "params": {
            "name": "start_certification",
            "arguments": {
                "application_id": "APP-MCP-01",
                "version": "1.0.0",
                "submission_id": "SUB-AGENTGEN-101",
                "trigger_type": "AGENT_SUBMISSION",
            },
        },
    }
    res = client.post("/api/v1/mcp", json=req)
    assert res.status_code == 200
    payload = res.json()
    assert "result" in payload
    cert_data = json.loads(payload["result"]["content"][0]["text"])
    cert_id = cert_data["certification_id"]
    assert cert_data["application_id"] == "APP-MCP-01"
    assert cert_data["version"] == "1.0.0"
    assert cert_data["status"] == CertificationStatusEnum.QUEUED.value

    # 2. tools/call -> get_certification_status
    status_req = {
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "tools/call",
        "params": {
            "name": "get_certification_status",
            "arguments": {"certification_id": cert_id},
        },
    }
    res_status = client.post("/api/v1/mcp", json=status_req)
    assert res_status.status_code == 200
    status_data = json.loads(res_status.json()["result"]["content"][0]["text"])
    assert status_data["certification_id"] == cert_id
    assert status_data["status"] == CertificationStatusEnum.QUEUED.value


def test_mcp_publication_status_deterministic(client, db_session):
    """get_publication_status returns deterministic READY_TO_PUBLISH or NOT_READY, never BLOCKED/REJECTED."""
    ApplicationService.create_application(
        db_session,
        ApplicationCreate(application_id="APP-MCP-PUB", name="Publication Check", version="2.5.0"),
    )

    # When no completed certification exists -> NOT_READY
    req = {
        "jsonrpc": "2.0",
        "id": "pub-1",
        "method": "tools/call",
        "params": {
            "name": "get_publication_status",
            "arguments": {"application_id": "APP-MCP-PUB", "version": "2.5.0"},
        },
    }
    res = client.post("/api/v1/mcp", json=req)
    assert res.status_code == 200
    data = json.loads(res.json()["result"]["content"][0]["text"])
    assert data["application_id"] == "APP-MCP-PUB"
    assert data["version"] == "2.5.0"
    assert data["publication_status"] == "NOT_READY"
    assert data["is_ready_to_publish"] is False
    assert data["publication_status"] not in ["BLOCKED", "REJECTED"]


def test_mcp_client_outbound_capability_call():
    """ACE as consumer can invoke external MCP server capabilities with JSON-RPC 2.0 format."""
    def mock_server_transport(request: httpx.Request):
        req_body = json.loads(request.content)
        assert req_body["method"] == "tools/call"
        assert req_body["params"]["name"] == "verify_application_documents"
        args = req_body["params"]["arguments"]
        assert args["application_id"] == "APP-OUTBOUND-1"
        assert args["version"] == "1.2.0"

        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": req_body["id"],
                "result": {
                    "structuredContent": {
                        "application_id": "APP-OUTBOUND-1",
                        "version": "1.2.0",
                        "run_id": "MCP-RUN-EXTERNAL-555",
                        "categories": {
                            cat: {"status": "PASS", "verified": True, "confidence": 0.96}
                            for cat in MANDATORY_17_DOC_CATEGORIES
                        },
                    }
                },
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_server_transport))
    mcp_consumer = ExternalMCPClient(http_client=mock_client)

    result = mcp_consumer.verify_documents_via_mcp(
        application_id="APP-OUTBOUND-1",
        version="1.2.0",
        server_url="https://mock-external-rag.local/mcp",
    )

    assert result.status == FindingStatusEnum.PASS
    assert result.verified_count == 17
    assert result.external_run_id == "MCP-RUN-EXTERNAL-555"
    assert len(result.category_verifications) == 17


def test_mcp_client_version_mismatch_remains_not_verified():
    """When external MCP returns mismatched version, client rejects it as NOT_VERIFIED."""
    def mock_mismatch_transport(request: httpx.Request):
        req_body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": req_body["id"],
                "result": {
                    "structuredContent": {
                        "application_id": "APP-MISMATCH",
                        "version": "0.9.0",  # Expected 1.0.0
                        "run_id": "MCP-RUN-MISMATCH",
                        "categories": {cat: {"status": "PASS", "verified": True} for cat in MANDATORY_17_DOC_CATEGORIES},
                    }
                },
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_mismatch_transport))
    mcp_consumer = ExternalMCPClient(http_client=mock_client)

    result = mcp_consumer.verify_documents_via_mcp(
        application_id="APP-MISMATCH",
        version="1.0.0",
        server_url="https://mock-external-rag.local/mcp",
    )

    assert result.status == FindingStatusEnum.NOT_VERIFIED
    assert "mismatched target" in result.description.lower()
