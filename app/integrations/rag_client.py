"""Real MyBlocks RAG integration client implementing DocumentVerifierProtocol.

Connects to the authoritative MyBlocks RAG system at https://myblocks.in/myblock_private
to verify compliance across all 17 mandatory document categories for the exact application and version.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.finding import FindingCategoryEnum, FindingStatusEnum
from app.integrations.contracts import (
    DocumentCategoryVerification,
    DocumentVerificationResult,
    DocumentVerifierProtocol,
    MANDATORY_17_DOC_CATEGORIES,
)
from app.mcp.client import ExternalMCPClient

logger = get_logger("ace.rag_client")


class MyBlocksRAGClient:
    """Production client for MyBlocks RAG document verification supporting both HTTP and MCP."""

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
        self.base_url = (base_url or settings.MYBLOCKS_RAG_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.MYBLOCKS_RAG_API_KEY
        self.timeout = timeout if timeout is not None else settings.MYBLOCKS_RAG_TIMEOUT
        self.mcp_url = mcp_url or settings.MYBLOCKS_RAG_MCP_URL
        self.mcp_auth_token = mcp_auth_token or settings.MYBLOCKS_RAG_MCP_AUTH_TOKEN
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

    def verify_application_documents(
        self,
        application_id: str,
        version: str,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> DocumentVerificationResult:
        """Verify the 17 mandatory document categories for exact application_id and version via MCP or HTTP."""
        logger.info(
            f"Querying MyBlocks RAG document verification for {application_id} (v{version})",
            extra={
                "event": "rag_verification_requested",
                "application_id": application_id,
                "version": version,
                "commit_hash": commit_hash,
                "submission_id": submission_id,
                "certification_id": certification_id,
                "target_url": self.base_url,
                "has_mcp": bool(self.mcp_client or self.mcp_url),
            },
        )

        # 1. Prefer MCP if configured
        if self.mcp_client:
            return self.mcp_client.verify_documents_via_mcp(
                application_id=application_id,
                version=version,
                server_url=self.mcp_url,
                auth_token=self.mcp_auth_token,
                commit_hash=commit_hash,
                submission_id=submission_id,
                certification_id=certification_id,
            )

        # 2. HTTP Fallback
        # If API key or explicit endpoint contract is not configured, surface the exact status
        # and return NOT_VERIFIED without fabricating success.
        if not self.api_key and not self._custom_client:
            return self._build_unconfigured_contract_result(
                application_id=application_id,
                version=version,
                reason=(
                    f"External MyBlocks RAG service at {self.base_url} requires authenticated API or MCP access. "
                    "Neither MYBLOCKS_RAG_MCP_URL nor MYBLOCKS_RAG_API_KEY is configured in environment, "
                    "and public unauthenticated verification is not available. All 17 document categories are NOT_VERIFIED."
                ),
            )

        client = self._get_client()
        try:
            # Send verification request to RAG endpoint
            payload = {
                "certification_id": certification_id,
                "application_id": application_id,
                "version": version,
                "commit_hash": commit_hash,
                "submission_id": submission_id,
                "categories": MANDATORY_17_DOC_CATEGORIES,
            }
            response = client.post("/api/v1/documents/verify", json=payload)

            if response.status_code == 200:
                data = response.json()
                return self._parse_rag_response(
                    application_id=application_id,
                    version=version,
                    data=data,
                )
            elif response.status_code in (401, 403):
                return self._build_unconfigured_contract_result(
                    application_id=application_id,
                    version=version,
                    reason=f"MyBlocks RAG returned authentication failure ({response.status_code}). Verify MYBLOCKS_RAG_API_KEY.",
                    raw_extra={"http_status": response.status_code},
                )
            else:
                return self._build_unconfigured_contract_result(
                    application_id=application_id,
                    version=version,
                    reason=f"MyBlocks RAG endpoint returned HTTP {response.status_code}: {response.text[:200]}",
                    raw_extra={"http_status": response.status_code, "response_body": response.text[:500]},
                )

        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning(
                f"MyBlocks RAG connection failed: {exc}",
                extra={
                    "event": "rag_connection_failed",
                    "application_id": application_id,
                    "version": version,
                    "error": str(exc),
                },
            )
            return self._build_unconfigured_contract_result(
                application_id=application_id,
                version=version,
                reason=f"Failed to connect to MyBlocks RAG at {self.base_url}: {str(exc)}",
                raw_extra={"connection_error": str(exc)},
            )
        finally:
            if self._custom_client is None:
                client.close()

    def _parse_rag_response(
        self,
        application_id: str,
        version: str,
        data: Dict[str, Any],
    ) -> DocumentVerificationResult:
        """Parse structured RAG response and enforce strict application/version matching."""
        if not isinstance(data, dict):
            return self._build_unconfigured_contract_result(
                application_id=application_id,
                version=version,
                reason="MyBlocks RAG returned malformed non-dictionary response.",
                raw_extra={"malformed_response": str(data)[:200]},
            )

        ext_app_id = data.get("application_id")
        ext_ver = data.get("version")
        ext_run_id = data.get("run_id") or data.get("rag_run_id")

        # Strict identity & version matching check:
        # Cross-version or cross-application evidence must NEVER be accepted.
        version_mismatch = (ext_ver is not None and ext_ver != version)
        app_mismatch = (ext_app_id is not None and ext_app_id != application_id)

        if version_mismatch or app_mismatch:
            mismatch_desc = (
                f"MyBlocks RAG reported evidence for mismatched target: "
                f"expected app '{application_id}' v{version}, received app '{ext_app_id}' v{ext_ver}."
            )
            logger.error(
                mismatch_desc,
                extra={
                    "event": "rag_identity_mismatch",
                    "expected_app": application_id,
                    "reported_app": ext_app_id,
                    "expected_version": version,
                    "reported_version": ext_ver,
                },
            )
            cat_verifications = [
                DocumentCategoryVerification(
                    category=cat,
                    requirement_id=f"DOC-{cat.replace('_', '-')}",
                    status=FindingStatusEnum.NOT_VERIFIED,
                    title=f"Document Requirement: {cat}",
                    description=mismatch_desc,
                    remediation=f"Re-index and verify documents in MyBlocks RAG for the exact application {application_id} and version {version}.",
                    source_version=ext_ver,
                    source_run_id=ext_run_id,
                    raw_evidence={"mismatch": True, "reported_version": ext_ver, "expected_version": version},
                )
                for cat in MANDATORY_17_DOC_CATEGORIES
            ]
            return DocumentVerificationResult(
                status=FindingStatusEnum.NOT_VERIFIED,
                category=FindingCategoryEnum.DOCUMENT,
                required_count=len(MANDATORY_17_DOC_CATEGORIES),
                verified_count=0,
                missing_categories=list(MANDATORY_17_DOC_CATEGORIES),
                title="RAG Identity / Version Discrepancy",
                description=mismatch_desc,
                remediation=f"Ensure MyBlocks RAG verifies the exact application '{application_id}' and version '{version}'.",
                raw_evidence={"discrepancy": mismatch_desc, "rag_response": data},
                external_run_id=ext_run_id,
                external_application_id=ext_app_id,
                external_version=ext_ver,
                category_verifications=cat_verifications,
            )

        # Parse per-category results
        verified_categories = []
        missing_categories = []
        cat_verifications: List[DocumentCategoryVerification] = []

        categories_data = data.get("categories", {})
        for cat in MANDATORY_17_DOC_CATEGORIES:
            req_id = f"DOC-{cat.replace('_', '-')}"
            cinfo = categories_data.get(cat)

            if isinstance(cinfo, dict) and cinfo.get("status") == "PASS" and cinfo.get("verified") is True:
                verified_categories.append(cat)
                cat_verifications.append(
                    DocumentCategoryVerification(
                        category=cat,
                        requirement_id=req_id,
                        status=FindingStatusEnum.PASS,
                        title=f"Document Requirement: {cat} (Verified)",
                        description=cinfo.get("summary") or f"Authoritative documentation for {cat} verified in MyBlocks RAG.",
                        confidence=cinfo.get("confidence"),
                        source_reference=cinfo.get("source_reference") or f"rag-doc://{application_id}/{version}/{cat}",
                        source_version=version,
                        source_run_id=ext_run_id,
                        source_timestamp=datetime.now(timezone.utc),
                        hash=cinfo.get("hash"),
                        raw_evidence=cinfo,
                    )
                )
            else:
                missing_categories.append(cat)
                reason_msg = (
                    cinfo.get("reason")
                    if isinstance(cinfo, dict) and cinfo.get("reason")
                    else f"Documentation for category '{cat}' not found or does not satisfy requirements in MyBlocks RAG."
                )
                cat_verifications.append(
                    DocumentCategoryVerification(
                        category=cat,
                        requirement_id=req_id,
                        status=FindingStatusEnum.NOT_VERIFIED,
                        title=f"Document Requirement: {cat}",
                        description=reason_msg,
                        remediation=f"Upload and index authoritative documentation for category '{cat}' in MyBlocks RAG for {application_id} v{version}.",
                        source_version=version,
                        source_run_id=ext_run_id,
                        raw_evidence=cinfo if isinstance(cinfo, dict) else {"verified": False, "category": cat},
                    )
                )

        all_passed = (len(verified_categories) == len(MANDATORY_17_DOC_CATEGORIES))
        overall_status = FindingStatusEnum.PASS if all_passed else FindingStatusEnum.NOT_VERIFIED

        return DocumentVerificationResult(
            status=overall_status,
            category=FindingCategoryEnum.DOCUMENT,
            required_count=len(MANDATORY_17_DOC_CATEGORIES),
            verified_count=len(verified_categories),
            missing_categories=missing_categories,
            title="MyBlocks RAG Document Verification",
            description=(
                f"{len(verified_categories)} of {len(MANDATORY_17_DOC_CATEGORIES)} mandatory "
                f"document categories verified for {application_id} (v{version})."
            ),
            remediation=(
                None if all_passed
                else f"Ingest missing categories ({', '.join(missing_categories[:5])}...) into MyBlocks RAG."
            ),
            raw_evidence=data,
            external_run_id=ext_run_id,
            external_application_id=ext_app_id or application_id,
            external_version=ext_ver or version,
            category_verifications=cat_verifications,
        )

    def _build_unconfigured_contract_result(
        self,
        application_id: str,
        version: str,
        reason: str,
        raw_extra: Optional[Dict[str, Any]] = None,
    ) -> DocumentVerificationResult:
        """Return deterministic NOT_VERIFIED result when RAG contract/credentials are absent."""
        cat_verifications = [
            DocumentCategoryVerification(
                category=cat,
                requirement_id=f"DOC-{cat.replace('_', '-')}",
                status=FindingStatusEnum.NOT_VERIFIED,
                title=f"Document Requirement: {cat}",
                description=f"Category '{cat}' is not verified. Reason: {reason}",
                remediation=(
                    f"Index authoritative documentation for category '{cat}' in MyBlocks RAG "
                    f"for {application_id} (v{version}) and configure valid RAG credentials."
                ),
                source_version=version,
                raw_evidence={"category": cat, "verified": False, "contract_status": "PENDING_OR_UNAUTHENTICATED"},
            )
            for cat in MANDATORY_17_DOC_CATEGORIES
        ]

        raw_evidence = {
            "integration": "MYBLOCKS_RAG",
            "base_url": self.base_url,
            "application_id": application_id,
            "version": version,
            "reason": reason,
            **(raw_extra or {}),
        }

        return DocumentVerificationResult(
            status=FindingStatusEnum.NOT_VERIFIED,
            category=FindingCategoryEnum.DOCUMENT,
            required_count=len(MANDATORY_17_DOC_CATEGORIES),
            verified_count=0,
            missing_categories=list(MANDATORY_17_DOC_CATEGORIES),
            title="MyBlocks RAG Document Verification Incomplete",
            description=reason,
            remediation=(
                "Authenticate with MyBlocks RAG and ensure all 17 mandatory document categories "
                f"are indexed for application '{application_id}' (v{version})."
            ),
            raw_evidence=raw_evidence,
            external_application_id=application_id,
            external_version=version,
            external_run_id=f"RAG-REQ-{application_id}-{version}",
            category_verifications=cat_verifications,
        )
