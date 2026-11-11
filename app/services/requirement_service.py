"""Service for managing compliance requirements and seeding mandatory standards."""

from typing import Dict, List
from sqlalchemy.orm import Session
from app.models.requirement import Requirement
from app.integrations.contracts import MANDATORY_17_DOC_CATEGORIES
from app.core.logging import get_logger

logger = get_logger("ace.requirement_service")

# Authoritative metadata for the 17 document requirements
MANDATORY_17_REQUIREMENTS_DEF: List[Dict[str, str]] = [
    {
        "category": "BRD",
        "name": "Business Requirements Document",
        "description": "Authoritative Business Requirements Document (BRD) defining business objectives and functional scope.",
    },
    {
        "category": "TRD",
        "name": "Technical Requirements Document",
        "description": "Technical Requirements Document (TRD) defining system architecture, tech stack, and engineering constraints.",
    },
    {
        "category": "SCOPE",
        "name": "Scope Definition Document",
        "description": "Project scope definition outlining system boundaries, in-scope functionality, and explicit exclusions.",
    },
    {
        "category": "SLA",
        "name": "Service Level Agreement",
        "description": "Service Level Agreement (SLA) specifying target availability, latency percentiles, and recovery objectives.",
    },
    {
        "category": "SOW",
        "name": "Statement of Work",
        "description": "Statement of Work (SOW) defining contractual deliverables, milestone criteria, and operational responsibilities.",
    },
    {
        "category": "MARKET_RESEARCH",
        "name": "Market Research Analysis",
        "description": "Market research and competitive analysis supporting product positioning and user persona needs.",
    },
    {
        "category": "FRD",
        "name": "Functional Requirements Document",
        "description": "Functional Requirements Document (FRD) outlining detailed operational capabilities and subsystem workflows.",
    },
    {
        "category": "USER_STORIES",
        "name": "User Stories Specification",
        "description": "User stories articulating actor roles, intended actions, and business value acceptance criteria.",
    },
    {
        "category": "USE_CASES",
        "name": "System Use Cases",
        "description": "Formal use case specifications covering primary flows, alternate paths, and exceptional error handling.",
    },
    {
        "category": "BUSINESS_LOGIC",
        "name": "Business Logic Documentation",
        "description": "Authoritative documentation of business rules, domain invariants, pricing/calculation algorithms, and policies.",
    },
    {
        "category": "TEST_PLAN",
        "name": "Test Plan",
        "description": "Verification strategy defining test methodologies, regression scopes, and quality gate criteria.",
    },
    {
        "category": "TEST_CASES",
        "name": "Test Cases Suite",
        "description": "Detailed test cases encompassing unit, integration, and end-to-end verification steps with expected outcomes.",
    },
    {
        "category": "API_DOCUMENTATION",
        "name": "API Documentation & Contract",
        "description": "Complete API documentation including route specifications, schema contracts, headers, and error codes.",
    },
    {
        "category": "AGENT_SPEC",
        "name": "Agent Specification",
        "description": "Agent specification defining autonomous behaviors, decision logic, tools, prompt guardrails, and constraints.",
    },
    {
        "category": "CR",
        "name": "Change Request Documentation",
        "description": "Change Request (CR) history detailing revisions, impact assessments, and architectural approvals.",
    },
    {
        "category": "PR",
        "name": "Pull Request & Review Audit",
        "description": "Pull request audit trails verifying peer reviews, automated build checks, and compliance approvals.",
    },
    {
        "category": "OTHER",
        "name": "Supporting Compliance Documentation",
        "description": "Supplementary compliance artifacts, certificates, or operational guides required for production certification.",
    },
]


class RequirementService:
    """Service to seed and query certification requirements."""

    @classmethod
    def seed_mandatory_requirements(cls, db: Session, policy_version: str = "v1.0") -> int:
        """Seed or update the 17 mandatory document requirements in the database.

        Idempotent: only inserts requirements that do not already exist.
        """
        created_count = 0
        for item in MANDATORY_17_REQUIREMENTS_DEF:
            req_id = f"DOC-{item['category'].replace('_', '-')}"
            existing = (
                db.query(Requirement)
                .filter(Requirement.requirement_id == req_id)
                .first()
            )
            if not existing:
                req = Requirement(
                    requirement_id=req_id,
                    category=item["category"],
                    name=item["name"],
                    description=item["description"],
                    mandatory=True,
                    active=True,
                    policy_version=policy_version,
                )
                db.add(req)
                created_count += 1

        if created_count > 0:
            db.commit()
            logger.info(
                f"Seeded {created_count} mandatory document requirements",
                extra={"event": "requirements_seeded", "count": created_count},
            )

        return created_count

    @classmethod
    def get_all_active_requirements(cls, db: Session) -> List[Requirement]:
        """Fetch all active compliance requirements."""
        return (
            db.query(Requirement)
            .filter(Requirement.active.is_(True))
            .order_by(Requirement.id.asc())
            .all()
        )
