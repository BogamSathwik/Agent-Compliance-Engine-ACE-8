"""Seed authoritative 17 document compliance requirements into requirements table.

Revision ID: 0003_seed_17_document_requirements
Revises: 0002_phase2_certification_models
Create Date: 2026-10-27 16:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column

revision: str = "0003_seed_17_document_requirements"
down_revision: Union[str, None] = "0002_phase2_certification_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REQUIREMENTS_SEED = [
    {
        "requirement_id": "DOC-BRD",
        "category": "BRD",
        "name": "Business Requirements Document",
        "description": "Authoritative Business Requirements Document (BRD) defining business objectives and functional scope.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-TRD",
        "category": "TRD",
        "name": "Technical Requirements Document",
        "description": "Technical Requirements Document (TRD) defining system architecture, tech stack, and engineering constraints.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-SCOPE",
        "category": "SCOPE",
        "name": "Scope Definition Document",
        "description": "Project scope definition outlining system boundaries, in-scope functionality, and explicit exclusions.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-SLA",
        "category": "SLA",
        "name": "Service Level Agreement",
        "description": "Service Level Agreement (SLA) specifying target availability, latency percentiles, and recovery objectives.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-SOW",
        "category": "SOW",
        "name": "Statement of Work",
        "description": "Statement of Work (SOW) defining contractual deliverables, milestone criteria, and operational responsibilities.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-MARKET-RESEARCH",
        "category": "MARKET_RESEARCH",
        "name": "Market Research Analysis",
        "description": "Market research and competitive analysis supporting product positioning and user persona needs.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-FRD",
        "category": "FRD",
        "name": "Functional Requirements Document",
        "description": "Functional Requirements Document (FRD) outlining detailed operational capabilities and subsystem workflows.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-USER-STORIES",
        "category": "USER_STORIES",
        "name": "User Stories Specification",
        "description": "User stories articulating actor roles, intended actions, and business value acceptance criteria.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-USE-CASES",
        "category": "USE_CASES",
        "name": "System Use Cases",
        "description": "Formal use case specifications covering primary flows, alternate paths, and exceptional error handling.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-BUSINESS-LOGIC",
        "category": "BUSINESS_LOGIC",
        "name": "Business Logic Documentation",
        "description": "Authoritative documentation of business rules, domain invariants, pricing/calculation algorithms, and policies.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-TEST-PLAN",
        "category": "TEST_PLAN",
        "name": "Test Plan",
        "description": "Verification strategy defining test methodologies, regression scopes, and quality gate criteria.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-TEST-CASES",
        "category": "TEST_CASES",
        "name": "Test Cases Suite",
        "description": "Detailed test cases encompassing unit, integration, and end-to-end verification steps with expected outcomes.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-API-DOCUMENTATION",
        "category": "API_DOCUMENTATION",
        "name": "API Documentation & Contract",
        "description": "Complete API documentation including route specifications, schema contracts, headers, and error codes.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-AGENT-SPEC",
        "category": "AGENT_SPEC",
        "name": "Agent Specification",
        "description": "Agent specification defining autonomous behaviors, decision logic, tools, prompt guardrails, and constraints.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-CR",
        "category": "CR",
        "name": "Change Request Documentation",
        "description": "Change Request (CR) history detailing revisions, impact assessments, and architectural approvals.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-PR",
        "category": "PR",
        "name": "Pull Request & Review Audit",
        "description": "Pull request audit trails verifying peer reviews, automated build checks, and compliance approvals.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
    {
        "requirement_id": "DOC-OTHER",
        "category": "OTHER",
        "name": "Supporting Compliance Documentation",
        "description": "Supplementary compliance artifacts, certificates, or operational guides required for production certification.",
        "mandatory": True,
        "active": True,
        "policy_version": "v1.0",
    },
]


def upgrade() -> None:
    requirements_table = table(
        "requirements",
        column("requirement_id", sa.String),
        column("category", sa.String),
        column("name", sa.String),
        column("description", sa.Text),
        column("mandatory", sa.Boolean),
        column("active", sa.Boolean),
        column("policy_version", sa.String),
    )

    op.bulk_insert(requirements_table, REQUIREMENTS_SEED)


def downgrade() -> None:
    req_ids = [r["requirement_id"] for r in REQUIREMENTS_SEED]
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM requirements WHERE requirement_id IN :req_ids"),
        {"req_ids": tuple(req_ids)},
    )
