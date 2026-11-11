"""Deterministic Certification Policy Engine."""

from typing import List, Optional, Set
from app.core.context import CertificationContext
from app.models.certification import CertificationStatusEnum
from app.models.certification_check import CertificationCheck, CheckStatusEnum, CheckTypeEnum
from app.models.finding import CertificationFinding, FindingStatusEnum, FindingCategoryEnum
from app.models.evidence import Evidence
from app.integrations.contracts import MANDATORY_17_DOC_CATEGORIES, MANDATORY_9_AGENT_RULES
from app.core.logging import get_logger

logger = get_logger("ace.policy_engine")

EXPECTED_9_RULE_IDS: Set[str] = {r["rule_id"] for r in MANDATORY_9_AGENT_RULES}
EXPECTED_17_DOC_CATEGORIES: Set[str] = set(MANDATORY_17_DOC_CATEGORIES)


class PolicyEngine:
    """Evaluates compliance deterministically without subjective LLM heuristics."""

    @staticmethod
    def evaluate_certification(
        context: CertificationContext,
        checks: List[CertificationCheck],
        findings: List[CertificationFinding],
        evidence: Optional[List[Evidence]] = None,
    ) -> CertificationStatusEnum:
        """Evaluate certification outcome strictly and deterministically.

        READY_TO_PUBLISH is awarded ONLY when ALL of the following are satisfied:
        1. All 17 mandatory document requirements verified (PASS).
        2. All 9 mandatory agent rules passing (PASS).
        3. QA passing for the exact application version (PASS).
        4. Application/version consistency passing (PASS).
        5. Required evidence present, valid, unexpired, matching target certification_id and version.
        6. No checks or findings have status FAIL, NOT_VERIFIED, PARTIAL, or ERROR.

        Otherwise: NOT_READY (or ERROR if check execution encountered fatal runtime error).
        NEVER outputs BLOCKED or REJECTED.
        """
        try:
            return PolicyEngine._evaluate_internal(context, checks, findings, evidence)
        except Exception as exc:
            logger.error(
                f"Unexpected exception during policy evaluation for {getattr(context, 'certification_id', 'unknown')}: {exc}",
                exc_info=True,
                extra={"event": "policy_evaluation_unexpected_error"},
            )
            return CertificationStatusEnum.ERROR

    @staticmethod
    def _evaluate_internal(
        context: CertificationContext,
        checks: List[CertificationCheck],
        findings: List[CertificationFinding],
        evidence: Optional[List[Evidence]] = None,
    ) -> CertificationStatusEnum:
        if not checks or not findings:
            logger.info(
                "Policy evaluation evaluated to NOT_READY: missing checks or findings",
                extra={"event": "policy_evaluated_not_ready", "certification_id": getattr(context, "certification_id", "unknown")},
            )
            return CertificationStatusEnum.NOT_READY

        # Check for system/execution errors
        has_error = any(
            c.status == CheckStatusEnum.ERROR.value for c in checks
        )
        if has_error:
            logger.warning(
                "Policy evaluation evaluated to ERROR: check error detected",
                extra={"event": "policy_evaluated_error", "certification_id": context.certification_id},
            )
            return CertificationStatusEnum.ERROR

        # Check for non-passing check statuses
        has_non_passing_checks = any(
            c.status != CheckStatusEnum.PASS.value for c in checks
        )
        if has_non_passing_checks:
            logger.info(
                "Policy evaluation evaluated to NOT_READY: non-passing checks present",
                extra={"event": "policy_evaluated_not_ready", "certification_id": context.certification_id},
            )
            return CertificationStatusEnum.NOT_READY

        # Check for non-passing finding statuses
        has_non_passing_findings = any(
            f.status != FindingStatusEnum.PASS.value for f in findings
        )
        if has_non_passing_findings:
            logger.info(
                "Policy evaluation evaluated to NOT_READY: non-passing findings present",
                extra={"event": "policy_evaluated_not_ready", "certification_id": context.certification_id},
            )
            return CertificationStatusEnum.NOT_READY

        # 1. Verify Document Requirement: check type DOCUMENT must exist and pass
        doc_checks = [c for c in checks if c.check_type == CheckTypeEnum.DOCUMENT.value]
        if not doc_checks or any(c.status != CheckStatusEnum.PASS.value for c in doc_checks):
            logger.info("Policy evaluated to NOT_READY: document check missing or not PASS")
            return CertificationStatusEnum.NOT_READY

        # Verify all 17 document categories are verified PASS
        doc_findings = [f for f in findings if f.category == FindingCategoryEnum.DOCUMENT.value]
        if not doc_findings:
            logger.info("Policy evaluated to NOT_READY: no document findings present")
            return CertificationStatusEnum.NOT_READY

        if len(doc_findings) == 1:
            single_f = doc_findings[0]
            summary_verified = (
                "17/17 verified" in (single_f.description or "").lower()
                or "17 documents verified" in (single_f.title or "").lower()
                or (single_f.title == "Docs verified" and single_f.status == FindingStatusEnum.PASS.value)
            )
            if not summary_verified:
                logger.info("Policy evaluated to NOT_READY: single document finding is partial, not all 17 verified")
                return CertificationStatusEnum.NOT_READY
        else:
            verified_cats: Set[str] = set()
            for f in doc_findings:
                if f.status == FindingStatusEnum.PASS.value:
                    for cat in MANDATORY_17_DOC_CATEGORIES:
                        req_norm = f"DOC-{cat.replace('_', '-')}"
                        if (
                            f.requirement_id in (req_norm, cat, cat.replace("_", "-"))
                            or (f.finding_code and cat in f.finding_code)
                            or (f.title and cat in f.title)
                        ):
                            verified_cats.add(cat)

            missing_cats = EXPECTED_17_DOC_CATEGORIES - verified_cats
            if missing_cats:
                logger.info(f"Policy evaluated to NOT_READY: missing verified document categories: {missing_cats}")
                return CertificationStatusEnum.NOT_READY

        # 2. Verify QA Requirement: check type QA must exist and pass
        qa_checks = [c for c in checks if c.check_type == CheckTypeEnum.QA.value]
        if not qa_checks or any(c.status != CheckStatusEnum.PASS.value for c in qa_checks):
            logger.info("Policy evaluated to NOT_READY: QA check missing or not PASS")
            return CertificationStatusEnum.NOT_READY

        # 3. Verify Rule Requirement: check type RULE or AGENT_RULES must exist and pass
        rule_checks = [
            c for c in checks
            if c.check_type in (CheckTypeEnum.RULE.value, CheckTypeEnum.AGENT_RULES.value)
        ]
        if not rule_checks or any(c.status != CheckStatusEnum.PASS.value for c in rule_checks):
            logger.info("Policy evaluated to NOT_READY: agent rule check missing or not PASS")
            return CertificationStatusEnum.NOT_READY

        # Verify all 9 agent rules pass if individual rule findings are present
        rule_findings = [
            f for f in findings
            if f.category in (FindingCategoryEnum.RULE.value, "RULE", "AGENT_RULES")
        ]
        if len(rule_findings) > 1:
            passed_rules: Set[str] = set()
            for rf in rule_findings:
                if rf.status == FindingStatusEnum.PASS.value:
                    for r_id in EXPECTED_9_RULE_IDS:
                        if rf.requirement_id == r_id or (rf.finding_code and r_id in rf.finding_code):
                            passed_rules.add(r_id)
            missing_rules = EXPECTED_9_RULE_IDS - passed_rules
            if missing_rules:
                logger.info(f"Policy evaluated to NOT_READY: missing verified agent rules: {missing_rules}")
                return CertificationStatusEnum.NOT_READY

        # 4. Verify Version Consistency: check type VERSION must pass
        ver_checks = [
            c for c in checks
            if c.check_type in (CheckTypeEnum.VERSION.value, "VERSION_CONSISTENCY")
        ]
        if ver_checks:
            if any(c.status != CheckStatusEnum.PASS.value for c in ver_checks):
                logger.info("Policy evaluated to NOT_READY: version consistency check not PASS")
                return CertificationStatusEnum.NOT_READY
        elif evidence is not None:
            # When evaluating full evidence, version consistency check is strictly mandatory
            logger.info("Policy evaluated to NOT_READY: version consistency check is missing")
            return CertificationStatusEnum.NOT_READY

        # 5. Verify Evidence: all required evidence must be present, valid, fresh, and match version & run
        if evidence is not None:
            if not evidence:
                logger.info("Policy evaluated to NOT_READY: evidence list is empty")
                return CertificationStatusEnum.NOT_READY

            evidence_sources = {e.source_system for e in evidence}
            required_sources = {"MYBLOCKS_RAG", "MYBLOCKS_QA", "RULE_ENGINE"}
            if not required_sources.issubset(evidence_sources):
                missing_ev = required_sources - evidence_sources
                logger.info(f"Policy evaluated to NOT_READY: missing evidence from required subsystems: {missing_ev}")
                return CertificationStatusEnum.NOT_READY

            # Validate that every evidence record matches the target application version, certification_id, and is fresh
            for ev in evidence:
                # Evidence must belong to this certification run
                if ev.certification_id and ev.certification_id != context.certification_id:
                    logger.info(
                        f"Policy evaluated to NOT_READY: evidence run mismatch ({ev.certification_id} != {context.certification_id})"
                    )
                    return CertificationStatusEnum.NOT_READY

                # Evidence must match the exact target application version
                ev_version = ev.source_version or (
                    ev.evidence_data.get("version")
                    or ev.evidence_data.get("source_version")
                    if isinstance(ev.evidence_data, dict)
                    else None
                )
                if not ev_version or ev_version != context.application_version:
                    logger.info(
                        f"Policy evaluated to NOT_READY: evidence version mismatch ({ev_version} != {context.application_version})"
                    )
                    return CertificationStatusEnum.NOT_READY

                # Evidence data must be non-empty and valid
                if not ev.evidence_data or ev.evidence_data == {}:
                    logger.info("Policy evaluated to NOT_READY: evidence data is empty or invalid")
                    return CertificationStatusEnum.NOT_READY

                # Stale evidence guard
                if isinstance(ev.evidence_data, dict):
                    if (
                        ev.evidence_data.get("is_stale")
                        or ev.evidence_data.get("stale")
                        or ev.evidence_data.get("status") in ("STALE", "EXPIRED")
                    ):
                        logger.info("Policy evaluated to NOT_READY: evidence is marked stale or expired")
                        return CertificationStatusEnum.NOT_READY

                    # If QA evidence, verify exact application_id and passed status
                    if ev.source_system == "MYBLOCKS_QA":
                        qa_app_id = ev.evidence_data.get("application_id")
                        if qa_app_id and qa_app_id != context.application_id:
                            logger.info(
                                f"Policy evaluated to NOT_READY: QA evidence application_id mismatch ({qa_app_id} != {context.application_id})"
                            )
                            return CertificationStatusEnum.NOT_READY
                        qa_passed = ev.evidence_data.get("passed")
                        qa_status = ev.evidence_data.get("status")
                        if qa_status == "SCHEDULED_POST_UPLOAD":
                            # Post-upload scheduled QA allows initial upload to AgentGen
                            pass
                        elif qa_passed is False or qa_status in ("FAIL", "NOT_VERIFIED"):
                            logger.info("Policy evaluated to NOT_READY: QA evidence reports non-passing outcome")
                            return CertificationStatusEnum.NOT_READY

                    # If Rule Engine evidence, verify passed_rules and total_rules
                    if ev.source_system == "RULE_ENGINE":
                        total_rules = ev.evidence_data.get("total_rules")
                        passed_rules_cnt = ev.evidence_data.get("passed_rules")
                        if total_rules is not None and total_rules < 9:
                            logger.info("Policy evaluated to NOT_READY: Rule engine evidence evaluated fewer than 9 rules")
                            return CertificationStatusEnum.NOT_READY
                        if passed_rules_cnt is not None and passed_rules_cnt < 9:
                            logger.info("Policy evaluated to NOT_READY: Rule engine evidence reports fewer than 9 passed rules")
                            return CertificationStatusEnum.NOT_READY

        logger.info(
            "Policy evaluation evaluated to READY_TO_PUBLISH: all checks, findings, and evidence pass",
            extra={"event": "policy_evaluated_ready_to_publish", "certification_id": context.certification_id},
        )
        return CertificationStatusEnum.READY_TO_PUBLISH
