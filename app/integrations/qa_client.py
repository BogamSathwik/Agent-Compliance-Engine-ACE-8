"""Real MyBlocks QA integration client implementing QAVerifierProtocol.

Connects to the authoritative MyBlocks QA application at https://myblocks.in/qa_app/
to verify automated test suite compliance for the exact application and version.
Uses MCP first via ExternalMCPClient, with authenticated HTTP fallback.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.finding import FindingCategoryEnum, FindingStatusEnum
from app.integrations.contracts import QAVerificationResult, QAVerifierProtocol
from app.mcp.client import ExternalMCPClient

logger = get_logger("ace.qa_client")


class MyBlocksQAClient:
    """Production client for MyBlocks QA authoritative test suite verification."""

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
        self.base_url = (base_url or settings.MYBLOCKS_QA_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.MYBLOCKS_QA_API_KEY
        self.timeout = timeout if timeout is not None else settings.MYBLOCKS_QA_TIMEOUT
        self.mcp_url = mcp_url or settings.MYBLOCKS_QA_MCP_URL
        self.mcp_auth_token = mcp_auth_token or settings.MYBLOCKS_QA_MCP_AUTH_TOKEN
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

    def verify_application_qa(
        self,
        application_id: str,
        version: str,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> QAVerificationResult:
        """Obtain authoritative QA evaluation for exact application_id and version."""
        logger.info(
            f"Querying MyBlocks QA verification for {application_id} (v{version})",
            extra={
                "event": "qa_verification_requested",
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
            return self.mcp_client.get_application_qa_status(
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
                    f"External MyBlocks QA service at {self.base_url} requires authenticated API or MCP access. "
                    "Neither MYBLOCKS_QA_MCP_URL nor MYBLOCKS_QA_API_KEY is configured in environment, "
                    "and public unauthenticated QA verification is not available. Authoritative QA is NOT_VERIFIED."
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
            response = client.post("/api/v1/qa/status", json=payload)

            if response.status_code == 200:
                data = response.json()
                return self._parse_qa_response(
                    application_id=application_id,
                    version=version,
                    data=data,
                )
            elif response.status_code in (401, 403):
                return self._build_unconfigured_contract_result(
                    application_id=application_id,
                    version=version,
                    reason=f"MyBlocks QA returned authentication failure ({response.status_code}). Verify MYBLOCKS_QA_API_KEY.",
                    raw_extra={"http_status": response.status_code},
                )
            else:
                return self._build_unconfigured_contract_result(
                    application_id=application_id,
                    version=version,
                    reason=f"MyBlocks QA endpoint returned HTTP {response.status_code}: {response.text[:200]}",
                    raw_extra={"http_status": response.status_code, "response_body": response.text[:500]},
                )

        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning(
                f"MyBlocks QA connection failed: {exc}",
                extra={
                    "event": "qa_connection_failed",
                    "application_id": application_id,
                    "version": version,
                    "error": str(exc),
                },
            )
            return self._build_unconfigured_contract_result(
                application_id=application_id,
                version=version,
                reason=f"Failed to connect to MyBlocks QA at {self.base_url}: {str(exc)}",
                raw_extra={"connection_error": str(exc)},
            )
        finally:
            if self._custom_client is None:
                client.close()

    def _parse_qa_response(
        self,
        application_id: str,
        version: str,
        data: Dict[str, Any],
    ) -> QAVerificationResult:
        """Parse structured QA response and enforce strict application/version matching."""
        if not isinstance(data, dict):
            return self._build_unconfigured_contract_result(
                application_id=application_id,
                version=version,
                reason="MyBlocks QA returned malformed non-dictionary response.",
                raw_extra={"malformed_response": str(data)[:200]},
            )

        ext_app = data.get("application_id")
        ext_ver = data.get("version")
        ext_run_id = data.get("run_id") or data.get("qa_run_id")

        # Strict identity & version matching check:
        # Cross-version or cross-application QA evidence must NEVER be accepted.
        version_mismatch = (ext_ver is not None and ext_ver != version)
        app_mismatch = (ext_app is not None and ext_app != application_id)

        if version_mismatch or app_mismatch:
            mismatch_desc = (
                f"MyBlocks QA reported evidence for mismatched target: "
                f"expected app '{application_id}' (v{version}), received app '{ext_app}' (v{ext_ver})."
            )
            logger.error(
                mismatch_desc,
                extra={
                    "event": "qa_identity_mismatch",
                    "expected_app": application_id,
                    "reported_app": ext_app,
                    "expected_version": version,
                    "reported_version": ext_ver,
                },
            )
            return QAVerificationResult(
                status=FindingStatusEnum.NOT_VERIFIED,
                category=FindingCategoryEnum.QA,
                passed=False,
                external_run_id=ext_run_id,
                external_application_id=ext_app,
                external_version=ext_ver,
                title="QA Identity / Version Discrepancy",
                description=mismatch_desc,
                remediation=f"Ensure MyBlocks QA runs for the exact application '{application_id}' and version '{version}'.",
                raw_evidence={"discrepancy": mismatch_desc, "qa_response": data},
            )

        pass_count = data.get("pass_count")
        fail_count = data.get("fail_count", 0)
        crit_fails = data.get("critical_failures", 0)
        explicit_status = str(data.get("status", "")).upper()
        explicit_passed = data.get("passed")

        is_passed = (
            (explicit_passed is True or explicit_status in ("PASS", "PASSED"))
            and crit_fails == 0
            and fail_count == 0
        )

        is_failed = (
            explicit_passed is False
            or explicit_status in ("FAIL", "FAILED")
            or fail_count > 0
            or crit_fails > 0
        )

        if is_passed:
            status = FindingStatusEnum.PASS
            desc = (
                data.get("summary")
                or f"Authoritative MyBlocks QA test suite passed for {application_id} (v{version}): {pass_count or 'all'} tests passed."
            )
            remed = None
        elif is_failed:
            status = FindingStatusEnum.FAIL
            desc = (
                data.get("summary")
                or f"MyBlocks QA test suite failed for {application_id} (v{version}): {fail_count} tests failed, {crit_fails} critical failures."
            )
            remed = f"Resolve {fail_count} failed tests and {crit_fails} critical issues in MyBlocks QA, then re-execute QA."
        else:
            status = FindingStatusEnum.NOT_VERIFIED
            desc = (
                data.get("summary")
                or f"Authoritative QA result for {application_id} (v{version}) is pending or incomplete in MyBlocks QA."
            )
            remed = f"Execute and complete the authoritative MyBlocks QA automated test suite for {application_id} (v{version})."

        return QAVerificationResult(
            status=status,
            category=FindingCategoryEnum.QA,
            passed=is_passed,
            qa_score=data.get("qa_score"),
            pass_count=pass_count,
            fail_count=fail_count,
            critical_failures=crit_fails,
            external_run_id=ext_run_id,
            external_application_id=ext_app or application_id,
            external_version=ext_ver or version,
            execution_timestamp=data.get("execution_timestamp") or datetime.now(timezone.utc),
            source_reference=data.get("source_reference") or f"qa-suite://{application_id}/{version}",
            confidence=data.get("confidence"),
            hash=data.get("hash"),
            title=f"MyBlocks QA Verification ({status.value})",
            description=desc,
            remediation=remed,
            raw_evidence=data,
        )

    def _build_unconfigured_contract_result(
        self,
        application_id: str,
        version: str,
        reason: str,
        raw_extra: Optional[Dict[str, Any]] = None,
    ) -> QAVerificationResult:
        raw_evidence = {
            "integration": "MYBLOCKS_QA",
            "base_url": self.base_url,
            "application_id": application_id,
            "version": version,
            "reason": reason,
            **(raw_extra or {}),
        }
        return QAVerificationResult(
            status=FindingStatusEnum.NOT_VERIFIED,
            category=FindingCategoryEnum.QA,
            passed=False,
            external_application_id=application_id,
            external_version=version,
            external_run_id=f"QA-REQ-{application_id}-{version}",
            title="MyBlocks QA Verification Incomplete",
            description=reason,
            remediation=(
                "Authenticate with MyBlocks QA and ensure the automated test suite "
                f"passes for application '{application_id}' (v{version})."
            ),
            raw_evidence=raw_evidence,
        )
