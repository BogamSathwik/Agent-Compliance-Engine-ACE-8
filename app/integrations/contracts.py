"""Future integration contracts and placeholder verifiers.

These define the explicit boundaries for:
1. MyBlocks RAG (17 document categories verification)
2. MyBlocks QA (Authoritative QA test suite)
3. 9-Rule Agent Evaluation Engine
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol
from app.models.finding import FindingCategoryEnum, FindingStatusEnum, FindingSeverityEnum


MANDATORY_17_DOC_CATEGORIES: List[str] = [
    "BRD",
    "TRD",
    "SCOPE",
    "SLA",
    "SOW",
    "MARKET_RESEARCH",
    "FRD",
    "USER_STORIES",
    "USE_CASES",
    "BUSINESS_LOGIC",
    "TEST_PLAN",
    "TEST_CASES",
    "API_DOCUMENTATION",
    "AGENT_SPEC",
    "CR",
    "PR",
    "OTHER",
]


@dataclass
class DocumentCategoryVerification:
    """Verification details for a single document requirement category."""
    category: str
    requirement_id: str
    status: FindingStatusEnum
    title: str
    description: str
    remediation: Optional[str] = None
    confidence: Optional[float] = None
    source_reference: Optional[str] = None
    source_version: Optional[str] = None
    source_run_id: Optional[str] = None
    source_timestamp: Optional[Any] = None
    hash: Optional[str] = None
    raw_evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentVerificationResult:
    """Result from MyBlocks RAG document verification across all 17 categories."""
    status: FindingStatusEnum
    category: FindingCategoryEnum = FindingCategoryEnum.DOCUMENT
    required_count: int = 17
    verified_count: int = 0
    missing_categories: List[str] = field(default_factory=list)
    title: str = "Document Verification"
    description: str = ""
    remediation: Optional[str] = None
    raw_evidence: Dict[str, Any] = field(default_factory=dict)
    external_run_id: Optional[str] = None
    external_application_id: Optional[str] = None
    external_version: Optional[str] = None
    category_verifications: List[DocumentCategoryVerification] = field(default_factory=list)


@dataclass
class QAVerificationResult:
    """Result from MyBlocks QA evaluation."""
    status: FindingStatusEnum
    category: FindingCategoryEnum = FindingCategoryEnum.QA
    passed: bool = False
    qa_score: Optional[float] = None
    pass_count: Optional[int] = None
    fail_count: Optional[int] = None
    critical_failures: Optional[int] = None
    external_run_id: Optional[str] = None
    external_application_id: Optional[str] = None
    external_version: Optional[str] = None
    execution_timestamp: Optional[Any] = None
    source_reference: Optional[str] = None
    confidence: Optional[float] = None
    hash: Optional[str] = None
    title: str = "QA Test Suite Verification"
    description: str = ""
    remediation: Optional[str] = None
    raw_evidence: Dict[str, Any] = field(default_factory=dict)


MANDATORY_9_AGENT_RULES: List[Dict[str, str]] = [
    {"rule_id": "RULE-1", "name": "Goal/objective", "category": "Core"},
    {"rule_id": "RULE-2", "name": "AI/LLM reasoning", "category": "Core for modern AI agents"},
    {"rule_id": "RULE-3", "name": "Ability to take actions", "category": "Core"},
    {"rule_id": "RULE-4", "name": "Tool/function calling", "category": "Usually"},
    {"rule_id": "RULE-5", "name": "Autonomous decision making", "category": "Core"},
    {"rule_id": "RULE-6", "name": "Execution/agent loop", "category": "Core"},
    {"rule_id": "RULE-7", "name": "Environment/context", "category": "Core"},
    {"rule_id": "RULE-8", "name": "Observation of results", "category": "Core"},
    {"rule_id": "RULE-9", "name": "Adaptation/re-planning", "category": "Strongly characteristic"},
]


@dataclass
class SingleRuleEvaluation:
    """Evaluation result for an individual agent rule."""
    rule_id: str
    rule_name: str
    category: str
    passed: bool
    status: FindingStatusEnum
    reason: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None
    is_mandatory: bool = True


@dataclass
class RuleEvaluationResult:
    """Result from 9-Rule agent compliance evaluation."""
    status: FindingStatusEnum
    category: FindingCategoryEnum = FindingCategoryEnum.RULE
    total_rules: int = 9
    passed_rules: int = 0
    failed_rules: int = 0
    missing_rules: List[str] = field(default_factory=list)
    passed: bool = False
    external_run_id: Optional[str] = None
    external_application_id: Optional[str] = None
    external_version: Optional[str] = None
    execution_timestamp: Optional[Any] = None
    source_reference: Optional[str] = None
    confidence: Optional[float] = None
    hash: Optional[str] = None
    title: str = "9-Rule Agent Compliance Evaluation"
    description: str = ""
    remediation: Optional[str] = None
    raw_evidence: Dict[str, Any] = field(default_factory=dict)
    rule_evaluations: List[SingleRuleEvaluation] = field(default_factory=list)


class DocumentVerifierProtocol(Protocol):
    """Protocol for MyBlocks RAG document verification."""

    def verify_application_documents(
        self,
        application_id: str,
        version: str,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> DocumentVerificationResult: ...


class QAVerifierProtocol(Protocol):
    """Protocol for MyBlocks QA authoritative test suite verification."""

    def verify_application_qa(
        self,
        application_id: str,
        version: str,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> QAVerificationResult: ...


class RuleEngineVerifierProtocol(Protocol):
    """Protocol for existing 9-rule agent evaluation application."""

    def evaluate_agent_rules(
        self,
        application_id: str,
        version: str,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> RuleEvaluationResult: ...


# =========================================================================
# Verifier Placeholders: explicitly mark as NOT_VERIFIED.
# Never fabricate passes or pretend external systems ran when they did not.
# =========================================================================

class Phase1DocumentVerifierPlaceholder:
    """Fallback placeholder for MyBlocks RAG document verification using the exact 17 categories."""

    MANDATORY_17_CATEGORIES = MANDATORY_17_DOC_CATEGORIES

    def verify_application_documents(
        self,
        application_id: str,
        version: str,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> DocumentVerificationResult:
        cat_verifications = [
            DocumentCategoryVerification(
                category=cat,
                requirement_id=f"DOC-{cat.replace('_', '-')}",
                status=FindingStatusEnum.NOT_VERIFIED,
                title=f"Document Requirement: {cat}",
                description=(
                    f"Document category '{cat}' for application '{application_id}' (v{version}) "
                    "has not been verified in MyBlocks RAG."
                ),
                remediation=(
                    f"Upload and index authoritative documentation for category '{cat}' "
                    f"in MyBlocks RAG for {application_id} v{version}."
                ),
                raw_evidence={"category": cat, "verified": False},
            )
            for cat in self.MANDATORY_17_CATEGORIES
        ]
        return DocumentVerificationResult(
            status=FindingStatusEnum.NOT_VERIFIED,
            category=FindingCategoryEnum.DOCUMENT,
            required_count=len(self.MANDATORY_17_CATEGORIES),
            verified_count=0,
            missing_categories=list(self.MANDATORY_17_CATEGORIES),
            title="MyBlocks RAG Document Verification Pending",
            description=(
                f"Document verification for application '{application_id}' (v{version}) "
                f"requires all {len(self.MANDATORY_17_CATEGORIES)} mandatory categories to be verified in MyBlocks RAG."
            ),
            remediation=(
                "Ingest and verify all 17 mandatory document categories via the MyBlocks RAG service "
                "before requesting publication certification."
            ),
            raw_evidence={
                "integration": "MYBLOCKS_RAG",
                "note": "Placeholder active; no synthetic pass fabricated.",
                "pending_categories": list(self.MANDATORY_17_CATEGORIES),
            },
            category_verifications=cat_verifications,
        )


class Phase1QAVerifierPlaceholder:
    """Phase 1 placeholder for MyBlocks QA test suite."""

    def verify_application_qa(
        self,
        application_id: str,
        version: str,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> QAVerificationResult:
        return QAVerificationResult(
            status=FindingStatusEnum.NOT_VERIFIED,
            category=FindingCategoryEnum.QA,
            passed=False,
            qa_score=None,
            title="MyBlocks QA Test Suite Verification Pending",
            description=(
                f"Authoritative QA verification for application '{application_id}' (v{version}, commit: {commit_hash or 'HEAD'}) "
                "is pending Phase 2 MyBlocks QA integration."
            ),
            remediation=(
                "Execute the authoritative MyBlocks QA automated test suite and ensure all test scenarios pass."
            ),
            raw_evidence={
                "integration": "MYBLOCKS_QA",
                "phase": 1,
                "note": "Placeholder active; no synthetic pass fabricated.",
            },
        )


class Phase1RuleEngineVerifierPlaceholder:
    """Phase 1 placeholder for 9-rule agent compliance evaluation."""

    def evaluate_agent_rules(
        self,
        application_id: str,
        version: str,
        commit_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
        certification_id: Optional[str] = None,
    ) -> RuleEvaluationResult:
        return RuleEvaluationResult(
            status=FindingStatusEnum.NOT_VERIFIED,
            category=FindingCategoryEnum.RULE,
            total_rules=9,
            passed_rules=0,
            title="9-Rule Agent Compliance Evaluation Pending",
            description=(
                f"Compliance evaluation across the 9 mandatory agent rules for application '{application_id}' "
                "is pending Phase 2 integration with the existing 9-rule scanner engine."
            ),
            remediation=(
                "Submit the agent codebase to the 9-rule scanner and resolve any non-compliant rules."
            ),
            raw_evidence={
                "integration": "RULE_ENGINE",
                "phase": 1,
                "note": "Placeholder active; no synthetic pass fabricated.",
                "total_rules": 9,
            },
        )
