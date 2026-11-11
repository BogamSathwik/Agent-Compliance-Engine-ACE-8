"""Existing 9-Rule Agent Evaluation MCP integration client implementing RuleEngineVerifierProtocol.

Connects to the external AgentGen / Agent Rule Evaluation application through MCP
to evaluate the 9 mandatory agent rules for the exact application and version.
Uses MCP first via ExternalMCPClient, with authenticated HTTP fallback.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.finding import FindingCategoryEnum, FindingStatusEnum
from app.integrations.contracts import RuleEvaluationResult, RuleEngineVerifierProtocol
from app.mcp.client import ExternalMCPClient

logger = get_logger("ace.rule_client")


class AgentRuleEvaluationClient:
    """Client for external 9-Rule Agent Evaluation application."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        http_client: Optional[httpx.Client] = None,
        mcp_url: Optional[str] = None,
        mcp_auth_token: Optional[str] = None,
        mcp_client: Optional[ExternalMCPClient] = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.RULE_ENGINE_BASE_URL or "").rstrip("/")
        self.api_key = api_key if api_key is not None else settings.RULE_ENGINE_API_KEY
        self.timeout = timeout if timeout is not None else settings.RULE_ENGINE_TIMEOUT
        self.mcp_url = mcp_url or settings.RULE_ENGINE_MCP_URL
        self.mcp_auth_token = mcp_auth_token or settings.RULE_ENGINE_MCP_AUTH_TOKEN
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
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "User-Agent": "ACE-ComplianceEngine/0.1.0",
                "Accept": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            follow_redirects=True,
        )

    def evaluate_agent_rules(
        self,
        application_id: str,
        version: str,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> RuleEvaluationResult:
        """Obtain authoritative 9-Rule evaluation for exact application_id and version."""
        logger.info(
            f"Querying 9-Rule agent evaluation for {application_id} (v{version})",
            extra={
                "event": "rule_evaluation_requested",
                "application_id": application_id,
                "version": version,
                "commit_hash": commit_hash,
                "submission_id": submission_id,
                "certification_id": certification_id,
                "target_url": self.base_url,
                "has_mcp": bool(self.mcp_client or self.mcp_url),
            },
        )

        # 1. MCP First
        if self.mcp_client:
            return self.mcp_client.evaluate_agent_rules(
                application_id=application_id,
                version=version,
                server_url=self.mcp_url,
                auth_token=self.mcp_auth_token,
                commit_hash=commit_hash,
                submission_id=submission_id,
                certification_id=certification_id,
            )

        # 2. HTTP Fallback
        if not self.api_key and not self._custom_client:
            return self._build_unconfigured_contract_result(
                application_id=application_id,
                version=version,
                reason=(
                    f"External 9-Rule Agent Evaluation application requires authenticated MCP or API access. "
                    "Neither RULE_ENGINE_MCP_URL nor RULE_ENGINE_API_KEY is configured in environment, "
                    "and public unauthenticated rule evaluation is not available. Rule evaluation is NOT_VERIFIED."
                ),
            )

        client = self._get_client()
        try:
            payload = {
                "certification_id": certification_id,
                "application_id": application_id,
                "version": version,
                "commit_hash": commit_hash,
                "submission_id": submission_id,
            }
            response = client.post("/api/v1/rules/evaluate", json=payload)

            if response.status_code == 200:
                data = response.json()
                # Parse using MCP client helper logic
                parser_client = self.mcp_client or ExternalMCPClient()
                return parser_client._parse_mcp_rule_response(
                    application_id=application_id,
                    version=version,
                    data=data,
                )
            elif response.status_code in (401, 403):
                return self._build_unconfigured_contract_result(
                    application_id=application_id,
                    version=version,
                    reason=f"Rule engine returned authentication failure ({response.status_code}). Verify RULE_ENGINE_API_KEY.",
                    raw_extra={"http_status": response.status_code},
                )
            else:
                return self._build_unconfigured_contract_result(
                    application_id=application_id,
                    version=version,
                    reason=f"Rule engine endpoint returned HTTP {response.status_code}: {response.text[:200]}",
                    raw_extra={"http_status": response.status_code, "response_body": response.text[:500]},
                )
        except Exception as exc:
            logger.warning(
                f"HTTP call to 9-Rule Engine at {self.base_url} failed: {exc}",
                extra={
                    "event": "rule_http_call_failed",
                    "application_id": application_id,
                    "version": version,
                    "target_url": self.base_url,
                    "error": str(exc),
                },
            )
            return self._build_unconfigured_contract_result(
                application_id=application_id,
                version=version,
                reason=f"Unable to reach 9-Rule Engine at {self.base_url}: {str(exc)}",
                raw_extra={"network_error": str(exc)},
            )
        finally:
            if self._custom_client is None:
                client.close()

    def _build_unconfigured_contract_result(
        self,
        application_id: str,
        version: str,
        reason: str,
        raw_extra: Optional[Dict[str, Any]] = None,
    ) -> RuleEvaluationResult:
        raw_evidence = {
            "integration": "RULE_ENGINE",
            "application_id": application_id,
            "version": version,
            "reason": reason,
            **(raw_extra or {}),
        }
        return RuleEvaluationResult(
            status=FindingStatusEnum.NOT_VERIFIED,
            category=FindingCategoryEnum.RULE,
            passed=False,
            total_rules=9,
            passed_rules=0,
            failed_rules=0,
            external_application_id=application_id,
            external_version=version,
            external_run_id=f"RULE-REQ-{application_id}-{version}",
            title="9-Rule Agent Compliance Evaluation Pending",
            description=reason,
            remediation=(
                f"Ensure 9-Rule Agent Evaluation MCP server (RULE_ENGINE_MCP_URL) or API (RULE_ENGINE_API_KEY) "
                f"is configured and reachable for application '{application_id}' (v{version})."
            ),
            raw_evidence=raw_evidence,
        )
