"""Integration contracts and service clients for ACE."""

from app.integrations.contracts import (
    DocumentCategoryVerification,
    DocumentVerificationResult,
    QAVerificationResult,
    RuleEvaluationResult,
    DocumentVerifierProtocol,
    QAVerifierProtocol,
    RuleEngineVerifierProtocol,
    SingleRuleEvaluation,
    Phase1DocumentVerifierPlaceholder,
    Phase1QAVerifierPlaceholder,
    Phase1RuleEngineVerifierPlaceholder,
    MANDATORY_17_DOC_CATEGORIES,
    MANDATORY_9_AGENT_RULES,
)
from app.integrations.rag_client import MyBlocksRAGClient
from app.integrations.qa_client import MyBlocksQAClient
from app.integrations.rule_client import AgentRuleEvaluationClient
from app.integrations.publication_client import (
    AgentGenPublicationClient,
    PublicationClientProtocol,
    ExternalPublicationResult,
)

__all__ = [
    "DocumentCategoryVerification",
    "DocumentVerificationResult",
    "QAVerificationResult",
    "RuleEvaluationResult",
    "SingleRuleEvaluation",
    "DocumentVerifierProtocol",
    "QAVerifierProtocol",
    "RuleEngineVerifierProtocol",
    "Phase1DocumentVerifierPlaceholder",
    "Phase1QAVerifierPlaceholder",
    "Phase1RuleEngineVerifierPlaceholder",
    "MANDATORY_17_DOC_CATEGORIES",
    "MANDATORY_9_AGENT_RULES",
    "MyBlocksRAGClient",
    "MyBlocksQAClient",
    "AgentRuleEvaluationClient",
    "AgentGenPublicationClient",
    "PublicationClientProtocol",
    "ExternalPublicationResult",
]

