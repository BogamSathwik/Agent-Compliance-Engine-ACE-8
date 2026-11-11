"""FastAPI router exposing ACE's MCP Server endpoint."""

from typing import Any, Dict
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.mcp.server import ACEMCPServer

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("", summary="Discover ACE MCP Server tools and capabilities")
def list_mcp_capabilities():
    """Return ACE MCP server protocol version, tool specifications, and schemas."""
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {
            "name": "ace-compliance-engine",
            "version": "0.1.0",
        },
        "capabilities": {
            "tools": ACEMCPServer.list_tools(),
        },
    }


@router.post("", summary="Execute standard JSON-RPC 2.0 MCP requests")
async def handle_mcp_request(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Handle incoming JSON-RPC 2.0 Model Context Protocol requests.

    Supported methods:
    - initialize
    - tools/list
    - tools/call
    - ping
    """
    settings = get_settings()

    # Optional authentication guard
    if settings.MCP_AUTH_TOKEN:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required for MCP server access",
            )
        token = authorization.split(" ", 1)[1]
        if token != settings.MCP_AUTH_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid MCP authorization token",
            )

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: invalid JSON payload"},
        }

    # Direct helper: allow simple {"tool": "name", "arguments": {...}} payloads as well
    if "tool" in body and "method" not in body:
        tool_name = body.get("tool")
        arguments = body.get("arguments", {})
        try:
            res = ACEMCPServer.call_tool(tool_name, arguments, db)
            return {"tool": tool_name, "result": res, "isError": False}
        except Exception as exc:
            return {"tool": tool_name, "error": str(exc), "isError": True}

    return ACEMCPServer.handle_jsonrpc(body, db)
