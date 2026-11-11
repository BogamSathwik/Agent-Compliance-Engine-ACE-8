"""ACE MCP Client - Connecting to external MCP servers.

Implements bidirectional MCP architecture (Direction A: ACE as a Consumer).
Enables ACE to query external MCP servers (e.g., MyBlocks RAG MCP, MyBlocks QA MCP,
and 9-Rule MCP) with strict identity propagation, correlation, and response verification.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.finding import FindingCategoryEnum, FindingStatusEnum
from app.integrations.contracts import (
    DocumentCategoryVerification,
    DocumentVerificationResult,
    QAVerificationResult,
    RuleEvaluationResult,
    SingleRuleEvaluation,
    MANDATORY_17_DOC_CATEGORIES,
    MANDATORY_9_AGENT_RULES,
)

logger = get_logger("ace.mcp.client")


class ExternalMCPClient:
    """Reusable client for invoking capabilities on external MCP servers."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout: Optional[float] = None,
        http_client: Optional[httpx.Client] = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or "").rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout if timeout is not None else 10.0
        self._custom_client = http_client

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client
        headers = {
            "User-Agent": "ACE-MCPClient/0.1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        return httpx.Client(
            headers=headers,
            timeout=self.timeout,
            follow_redirects=True,
        )

    def call_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: Dict[str, Any],
        auth_token: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a standard JSON-RPC 2.0 tools/call request to an external MCP server."""
        url = server_url.rstrip("/")
        # If url doesn't end with /mcp, standard MCP HTTP endpoint is often at /mcp or root
        post_url = url if url.endswith("/mcp") else f"{url}/mcp"

        payload = {
            "jsonrpc": "2.0",
            "id": f"ace-mcp-req-{int(datetime.now(timezone.utc).timestamp())}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        headers = {
            "User-Agent": "ACE-MCPClient/0.1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        effective_token = auth_token or self.auth_token
        if effective_token:
            headers["Authorization"] = f"Bearer {effective_token}"

        client = self._custom_client or httpx.Client(
            headers=headers,
            timeout=timeout or self.timeout,
            follow_redirects=True,
        )

        try:
            logger.info(
                f"Dispatching outbound MCP tool call '{tool_name}' to {post_url}",
                extra={"event": "outbound_mcp_call", "tool_name": tool_name, "target_url": post_url},
            )
            response = client.post(post_url, json=payload)
            if response.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"External MCP server returned HTTP {response.status_code}: {response.text[:200]}",
                    request=response.request,
                    response=response,
                )

            data = response.json()
            if "error" in data:
                err = data["error"]
                raise RuntimeError(f"MCP server error ({err.get('code')}): {err.get('message')}")

            result = data.get("result", {})
            # MCP tools/call responses can contain content text or structuredContent
            if "structuredContent" in result:
                return result["structuredContent"]
            elif "content" in result and isinstance(result["content"], list) and result["content"]:
                first_content = result["content"][0]
                if isinstance(first_content, dict) and first_content.get("type") == "text":
                    try:
                        return json.loads(first_content.get("text", "{}"))
                    except json.JSONDecodeError:
                        return {"text": first_content.get("text")}
            return result
        finally:
            if self._custom_client is None:
                client.close()

    def verify_documents_via_mcp(
        self,
        application_id: str,
        version: str,
        server_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> DocumentVerificationResult:
        """Call external MyBlocks RAG MCP tool to verify documents with strict identity validation."""
        target_url = server_url or self.base_url
        if not target_url:
            return self._build_unconfigured_result(
                application_id=application_id,
                version=version,
                reason="MYBLOCKS_RAG_MCP_URL is not configured in environment.",
            )

        arguments = {
            "application_id": application_id,
            "version": version,
            "commit_hash": commit_hash,
            "submission_id": submission_id,
            "certification_id": certification_id,
            "categories": MANDATORY_17_DOC_CATEGORIES,
        }

        try:
            mcp_response = self.call_tool(
                server_url=target_url,
                tool_name="verify_application_documents",
                arguments=arguments,
                auth_token=auth_token,
            )
            return self._parse_mcp_rag_response(
                application_id=application_id,
                version=version,
                data=mcp_response,
            )
        except Exception as exc:
            logger.warning(
                f"External MyBlocks RAG MCP call failed: {exc}",
                extra={
                    "event": "mcp_rag_call_failed",
                    "application_id": application_id,
                    "version": version,
                    "target_url": target_url,
                    "error": str(exc),
                },
            )
            return self._build_unconfigured_result(
                application_id=application_id,
                version=version,
                reason=f"Failed to query MyBlocks RAG via MCP at {target_url}: {str(exc)}",
                raw_extra={"mcp_error": str(exc)},
            )

    def _parse_mcp_rag_response(
        self,
        application_id: str,
        version: str,
        data: Dict[str, Any],
    ) -> DocumentVerificationResult:
        """Parse external MCP RAG response and validate strict identity matching."""
        if not isinstance(data, dict):
            return self._build_unconfigured_result(
                application_id=application_id,
                version=version,
                reason="External MCP RAG returned malformed non-dictionary response.",
                raw_extra={"malformed_data": str(data)[:200]},
            )

        ext_app = data.get("application_id")
        ext_ver = data.get("version")
        ext_run_id = data.get("run_id") or data.get("mcp_run_id") or data.get("rag_run_id")

        # Identity & Version validation: cross-version evidence must be rejected
        if (ext_app and ext_app != application_id) or (ext_ver and ext_ver != version):
            mismatch_desc = (
                f"External MCP RAG returned evidence for mismatched target: "
                f"expected app '{application_id}' (v{version}), received app '{ext_app}' (v{ext_ver})."
            )
            logger.error(mismatch_desc, extra={"event": "mcp_identity_mismatch"})
            cat_verifications = [
                DocumentCategoryVerification(
                    category=cat,
                    requirement_id=f"DOC-{cat.replace('_', '-')}",
                    status=FindingStatusEnum.NOT_VERIFIED,
                    title=f"Document Requirement: {cat}",
                    description=mismatch_desc,
                    remediation=f"Re-verify {cat} in MyBlocks RAG for the exact application {application_id} and version {version}.",
                    source_version=ext_ver,
                    source_run_id=ext_run_id,
                    raw_evidence={"mismatch": True, "reported_version": ext_ver},
                )
                for cat in MANDATORY_17_DOC_CATEGORIES
            ]
            return DocumentVerificationResult(
                status=FindingStatusEnum.NOT_VERIFIED,
                category=FindingCategoryEnum.DOCUMENT,
                required_count=len(MANDATORY_17_DOC_CATEGORIES),
                verified_count=0,
                missing_categories=list(MANDATORY_17_DOC_CATEGORIES),
                title="MCP Identity / Version Discrepancy",
                description=mismatch_desc,
                remediation=f"Ensure MyBlocks RAG MCP verifies the exact application '{application_id}' and version '{version}'.",
                raw_evidence={"discrepancy": mismatch_desc, "mcp_response": data},
                external_run_id=ext_run_id,
                external_application_id=ext_app,
                external_version=ext_ver,
                category_verifications=cat_verifications,
            )

        # Parse per-category results
        verified_categories = []
        missing_categories = []
        cat_verifications: List[DocumentCategoryVerification] = []

        categories_data = data.get("categories") or data.get("documents") or {}
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
                        title=f"Document Requirement: {cat} (Verified via MCP)",
                        description=cinfo.get("summary") or f"Authoritative documentation for {cat} verified via MyBlocks RAG MCP.",
                        confidence=cinfo.get("confidence"),
                        source_reference=cinfo.get("source_reference") or f"mcp-rag://{application_id}/{version}/{cat}",
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
                    else f"Documentation for category '{cat}' not verified via MyBlocks RAG MCP."
                )
                cat_verifications.append(
                    DocumentCategoryVerification(
                        category=cat,
                        requirement_id=req_id,
                        status=FindingStatusEnum.NOT_VERIFIED,
                        title=f"Document Requirement: {cat}",
                        description=reason_msg,
                        remediation=f"Index category '{cat}' in MyBlocks RAG for {application_id} v{version}.",
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
            title="MyBlocks RAG MCP Document Verification",
            description=f"{len(verified_categories)} of {len(MANDATORY_17_DOC_CATEGORIES)} categories verified via MCP for {application_id} v{version}.",
            remediation=None if all_passed else f"Ingest missing categories ({', '.join(missing_categories[:4])}...) in MyBlocks RAG.",
            raw_evidence=data,
            external_run_id=ext_run_id,
            external_application_id=ext_app or application_id,
            external_version=ext_ver or version,
            category_verifications=cat_verifications,
        )

    def _build_unconfigured_result(
        self,
        application_id: str,
        version: str,
        reason: str,
        raw_extra: Optional[Dict[str, Any]] = None,
    ) -> DocumentVerificationResult:
        cat_verifications = [
            DocumentCategoryVerification(
                category=cat,
                requirement_id=f"DOC-{cat.replace('_', '-')}",
                status=FindingStatusEnum.NOT_VERIFIED,
                title=f"Document Requirement: {cat}",
                description=f"Category '{cat}' is not verified via MCP. Reason: {reason}",
                remediation=(
                    f"Configure MyBlocks RAG MCP server and index category '{cat}' "
                    f"for {application_id} (v{version})."
                ),
                source_version=version,
                raw_evidence={"category": cat, "verified": False, "mcp_status": "UNCONFIGURED_OR_UNREACHABLE"},
            )
            for cat in MANDATORY_17_DOC_CATEGORIES
        ]

        raw_evidence = {
            "integration": "MYBLOCKS_RAG_MCP",
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
            title="MyBlocks RAG MCP Verification Incomplete",
            description=reason,
            remediation=f"Ensure MyBlocks RAG MCP server is running and reachable for application '{application_id}' (v{version}).",
            raw_evidence=raw_evidence,
            external_application_id=application_id,
            external_version=version,
            external_run_id=f"MCP-REQ-{application_id}-{version}",
            category_verifications=cat_verifications,
        )

    def get_application_qa_status(
        self,
        application_id: str,
        version: str,
        server_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> QAVerificationResult:
        """Query external MyBlocks QA MCP server with exact application/version identity."""
        target_url = server_url or self.base_url
        if not target_url:
            return self._build_unconfigured_qa_result(
                application_id=application_id,
                version=version,
                reason="MYBLOCKS_QA_MCP_URL is not configured in environment.",
            )

        arguments = {
            "application_id": application_id,
            "version": version,
            "commit_hash": commit_hash,
            "submission_id": submission_id,
            "certification_id": certification_id,
        }

        try:
            mcp_response = self.call_tool(
                server_url=target_url,
                tool_name="get_application_qa_status",
                arguments=arguments,
                auth_token=auth_token,
            )
            return self._parse_mcp_qa_response(
                application_id=application_id,
                version=version,
                data=mcp_response,
            )
        except Exception as exc:
            logger.warning(
                f"External MyBlocks QA MCP call failed: {exc}",
                extra={
                    "event": "mcp_qa_call_failed",
                    "application_id": application_id,
                    "version": version,
                    "target_url": target_url,
                    "error": str(exc),
                },
            )
            return self._build_unconfigured_qa_result(
                application_id=application_id,
                version=version,
                reason=f"Failed to query MyBlocks QA via MCP at {target_url}: {str(exc)}",
                raw_extra={"mcp_error": str(exc)},
            )

    def _parse_mcp_qa_response(
        self,
        application_id: str,
        version: str,
        data: Dict[str, Any],
    ) -> QAVerificationResult:
        """Parse external MCP QA response and enforce strict application/version matching."""
        if not isinstance(data, dict):
            return self._build_unconfigured_qa_result(
                application_id=application_id,
                version=version,
                reason="External MCP QA returned malformed non-dictionary response.",
                raw_extra={"malformed_data": str(data)[:200]},
            )

        ext_app = data.get("application_id")
        ext_ver = data.get("version")
        ext_run_id = data.get("run_id") or data.get("qa_run_id") or data.get("mcp_run_id")

        # Identity & Version validation: cross-version evidence must be rejected
        if (ext_app and ext_app != application_id) or (ext_ver and ext_ver != version):
            mismatch_desc = (
                f"External MCP QA returned evidence for mismatched target: "
                f"expected app '{application_id}' (v{version}), received app '{ext_app}' (v{ext_ver})."
            )
            logger.error(mismatch_desc, extra={"event": "mcp_qa_identity_mismatch"})
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
                raw_evidence={"discrepancy": mismatch_desc, "mcp_response": data},
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
            source_reference=data.get("source_reference") or f"mcp-qa://{application_id}/{version}",
            confidence=data.get("confidence"),
            hash=data.get("hash"),
            title=f"MyBlocks QA Verification ({status.value})",
            description=desc,
            remediation=remed,
            raw_evidence=data,
        )

    def _build_unconfigured_qa_result(
        self,
        application_id: str,
        version: str,
        reason: str,
        raw_extra: Optional[Dict[str, Any]] = None,
    ) -> QAVerificationResult:
        raw_evidence = {
            "integration": "MYBLOCKS_QA_MCP",
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
            external_run_id=f"MCP-QA-REQ-{application_id}-{version}",
            title="MyBlocks QA MCP Verification Incomplete",
            description=reason,
            remediation=(
                f"Ensure MyBlocks QA MCP server is configured and authoritative tests pass "
                f"for application '{application_id}' (v{version})."
            ),
            raw_evidence=raw_evidence,
        )

    def evaluate_agent_rules(
        self,
        application_id: str,
        version: str,
        server_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> RuleEvaluationResult:
        """Query external 9-Rule Agent Evaluation MCP server with exact application/version identity."""
        target_url = server_url or self.base_url
        if not target_url:
            return self._build_unconfigured_rule_result(
                application_id=application_id,
                version=version,
                reason="RULE_ENGINE_MCP_URL is not configured in environment.",
            )

        arguments = {
            "application_id": application_id,
            "version": version,
            "commit_hash": commit_hash,
            "submission_id": submission_id,
            "certification_id": certification_id,
        }

        try:
            mcp_response = self.call_tool(
                server_url=target_url,
                tool_name="evaluate_agent_rules",
                arguments=arguments,
                auth_token=auth_token,
            )
            return self._parse_mcp_rule_response(
                application_id=application_id,
                version=version,
                data=mcp_response,
            )
        except Exception as exc:
            logger.warning(
                f"External 9-Rule MCP call failed: {exc}",
                extra={
                    "event": "mcp_rule_call_failed",
                    "application_id": application_id,
                    "version": version,
                    "target_url": target_url,
                    "error": str(exc),
                },
            )
            return self._build_unconfigured_rule_result(
                application_id=application_id,
                version=version,
                reason=f"Failed to query 9-Rule evaluation engine via MCP at {target_url}: {str(exc)}",
                raw_extra={"mcp_error": str(exc)},
            )

    def _parse_mcp_rule_response(
        self,
        application_id: str,
        version: str,
        data: Dict[str, Any],
    ) -> RuleEvaluationResult:
        """Parse external MCP 9-Rule response and enforce strict identity, completeness, and pass/fail rules."""
        if not isinstance(data, dict):
            return self._build_unconfigured_rule_result(
                application_id=application_id,
                version=version,
                reason="External MCP Rule Engine returned malformed non-dictionary response.",
                raw_extra={"malformed_data": str(data)[:200]},
            )

        ext_app = data.get("application_id")
        ext_ver = data.get("version")
        ext_run_id = (
            data.get("run_id")
            or data.get("evaluation_id")
            or data.get("rule_run_id")
            or data.get("mcp_run_id")
        )

        # Identity & Version validation: cross-version evidence must be rejected
        if (ext_app and ext_app != application_id) or (ext_ver and ext_ver != version):
            mismatch_desc = (
                f"External MCP Rule Engine returned evidence for mismatched target: "
                f"expected app '{application_id}' (v{version}), received app '{ext_app}' (v{ext_ver})."
            )
            logger.error(mismatch_desc, extra={"event": "mcp_rule_identity_mismatch"})
            return RuleEvaluationResult(
                status=FindingStatusEnum.NOT_VERIFIED,
                category=FindingCategoryEnum.RULE,
                passed=False,
                total_rules=9,
                passed_rules=0,
                failed_rules=0,
                external_run_id=ext_run_id,
                external_application_id=ext_app,
                external_version=ext_ver,
                title="Rule Engine Identity / Version Discrepancy",
                description=mismatch_desc,
                remediation=f"Ensure 9-Rule Evaluation runs for the exact application '{application_id}' and version '{version}'.",
                raw_evidence={"discrepancy": mismatch_desc, "mcp_response": data},
            )

        # Extract rules from response
        raw_rules = data.get("rules")
        if raw_rules is None:
            raw_rules = data.get("rule_results")
        if raw_rules is None:
            raw_rules = data.get("results")

        rule_evaluations: List[SingleRuleEvaluation] = []
        missing_rules: List[str] = []

        # Normalize incoming raw_rules into a lookup structure
        parsed_entries: Dict[str, Dict[str, Any]] = {}
        if isinstance(raw_rules, list):
            for item in raw_rules:
                if isinstance(item, dict):
                    name_key = str(
                        item.get("name")
                        or item.get("rule_name")
                        or item.get("rule_id")
                        or item.get("rule")
                        or ""
                    ).strip().lower()
                    if name_key:
                        parsed_entries[name_key] = item
        elif isinstance(raw_rules, dict):
            for k, v in raw_rules.items():
                name_key = str(k).strip().lower()
                if isinstance(v, dict):
                    parsed_entries[name_key] = v
                elif isinstance(v, bool):
                    parsed_entries[name_key] = {"passed": v, "status": "PASS" if v else "FAIL"}
                elif isinstance(v, str):
                    parsed_entries[name_key] = {"passed": v.upper() == "PASS", "status": v.upper()}
        elif isinstance(data, dict):
            for k, v in data.items():
                name_key = str(k).strip().lower()
                if isinstance(v, dict) and ("passed" in v or "status" in v):
                    parsed_entries[name_key] = v

        def find_rule_match(rule_id: str, rule_name: str) -> Optional[Dict[str, Any]]:
            rid_lower = rule_id.lower()
            rname_lower = rule_name.lower()
            if rid_lower in parsed_entries:
                return parsed_entries[rid_lower]
            if rname_lower in parsed_entries:
                return parsed_entries[rname_lower]
            for k, entry in parsed_entries.items():
                if rid_lower in k or k in rid_lower:
                    return entry
                name_parts = [p.strip() for p in rname_lower.replace("/", " ").replace("-", " ").split()]
                if all(part in k for part in name_parts[:2]):
                    return entry
                if rname_lower in k or k in rname_lower:
                    return entry
            return None

        passed_count = 0
        failed_count = 0

        for rule_meta in MANDATORY_9_AGENT_RULES:
            r_id = rule_meta["rule_id"]
            r_name = rule_meta["name"]
            r_cat = rule_meta["category"]

            matched = find_rule_match(r_id, r_name)
            if matched is None:
                missing_rules.append(r_name)
                continue

            p_val = matched.get("passed")
            st_val = str(matched.get("status", "")).upper()

            is_rule_passed = (
                (p_val is True or st_val in ("PASS", "PASSED"))
                and p_val is not False
                and st_val not in ("FAIL", "FAILED")
            )
            status_enum = FindingStatusEnum.PASS if is_rule_passed else FindingStatusEnum.FAIL

            if is_rule_passed:
                passed_count += 1
            else:
                failed_count += 1

            rule_eval = SingleRuleEvaluation(
                rule_id=r_id,
                rule_name=r_name,
                category=r_cat,
                passed=is_rule_passed,
                status=status_enum,
                reason=matched.get("reason") or matched.get("explanation") or matched.get("description"),
                evidence=matched.get("evidence") or matched.get("raw_evidence"),
                is_mandatory=True,
            )
            rule_evaluations.append(rule_eval)

        # Completeness Check:
        # If any of the 9 mandatory rules is missing, response is incomplete -> NOT_VERIFIED
        if missing_rules or len(rule_evaluations) < 9:
            missing_str = ", ".join(missing_rules) if missing_rules else f"{9 - len(rule_evaluations)} rules"
            desc = (
                f"External 9-Rule evaluation response is incomplete for {application_id} (v{version}): "
                f"missing mandatory rules [{missing_str}]."
            )
            logger.warning(desc, extra={"event": "mcp_rule_incomplete", "missing_rules": missing_rules})
            return RuleEvaluationResult(
                status=FindingStatusEnum.NOT_VERIFIED,
                category=FindingCategoryEnum.RULE,
                total_rules=9,
                passed_rules=passed_count,
                failed_rules=failed_count,
                missing_rules=missing_rules,
                passed=False,
                external_run_id=ext_run_id,
                external_application_id=ext_app or application_id,
                external_version=ext_ver or version,
                execution_timestamp=data.get("execution_timestamp") or datetime.now(timezone.utc),
                source_reference=data.get("source_reference") or f"mcp-rules://{application_id}/{version}",
                confidence=data.get("confidence"),
                hash=data.get("hash"),
                title="9-Rule Evaluation Incomplete",
                description=desc,
                remediation=f"Ensure the external rule evaluation engine executes and reports all 9 mandatory rules for {application_id} (v{version}).",
                raw_evidence=data,
                rule_evaluations=rule_evaluations,
            )

        overall_status_str = str(data.get("status", "")).upper()
        overall_passed_val = data.get("passed")

        is_passed = (
            failed_count == 0
            and passed_count == 9
            and (overall_passed_val is not False)
            and overall_status_str not in ("FAIL", "FAILED")
        )

        if is_passed:
            status = FindingStatusEnum.PASS
            desc = (
                data.get("summary")
                or f"All 9 mandatory agent rules evaluated and verified passed for {application_id} (v{version})."
            )
            remed = None
        else:
            status = FindingStatusEnum.FAIL
            failed_names = [r.rule_name for r in rule_evaluations if not r.passed]
            desc = (
                data.get("summary")
                or f"9-Rule agent compliance evaluation failed for {application_id} (v{version}): "
                f"{failed_count} rule(s) failed ({', '.join(failed_names)})."
            )
            remed = f"Remediate agent architecture and behavior for failed rules: {', '.join(failed_names)}."

        return RuleEvaluationResult(
            status=status,
            category=FindingCategoryEnum.RULE,
            total_rules=9,
            passed_rules=passed_count,
            failed_rules=failed_count,
            missing_rules=[],
            passed=is_passed,
            external_run_id=ext_run_id,
            external_application_id=ext_app or application_id,
            external_version=ext_ver or version,
            execution_timestamp=data.get("execution_timestamp") or datetime.now(timezone.utc),
            source_reference=data.get("source_reference") or f"mcp-rules://{application_id}/{version}",
            confidence=data.get("confidence"),
            hash=data.get("hash"),
            title=f"9-Rule Agent Compliance ({status.value})",
            description=desc,
            remediation=remed,
            raw_evidence=data,
            rule_evaluations=rule_evaluations,
        )

    def _build_unconfigured_rule_result(
        self,
        application_id: str,
        version: str,
        reason: str,
        raw_extra: Optional[Dict[str, Any]] = None,
    ) -> RuleEvaluationResult:
        raw_evidence = {
            "integration": "RULE_ENGINE_MCP",
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
            external_run_id=f"MCP-RULE-REQ-{application_id}-{version}",
            title="9-Rule Evaluation MCP Verification Incomplete",
            description=reason,
            remediation=(
                f"Ensure 9-Rule Agent Evaluation MCP server is configured and reachable "
                f"for application '{application_id}' (v{version})."
            ),
            raw_evidence=raw_evidence,
        )


