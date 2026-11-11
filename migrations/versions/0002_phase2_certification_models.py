"""Phase 2 certification models, versions, checks, requirements, and integration runs.

Revision ID: 0002_phase2_certification_models
Revises: 0001_initial_ace_tables
Create Date: 2026-10-27 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002_phase2_certification_models"
down_revision: Union[str, None] = "0001_initial_ace_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create application_versions table
    op.create_table(
        "application_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("commit_hash", sa.String(length=128), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("submission_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.application_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", "version", name="uq_application_versions_app_version"),
    )
    op.create_index("ix_application_versions_application_id", "application_versions", ["application_id"])
    op.create_index("ix_application_versions_version", "application_versions", ["version"])
    op.create_index("ix_application_versions_app_commit", "application_versions", ["application_id", "commit_hash"])

    # 2. Alter certification_runs to add version link, submission ID, trigger type, and policy version
    op.add_column("certification_runs", sa.Column("application_version_id", sa.Integer(), nullable=True))
    op.add_column("certification_runs", sa.Column("submission_id", sa.String(length=64), nullable=True))
    op.add_column("certification_runs", sa.Column("trigger_type", sa.String(length=64), server_default="MANUAL", nullable=False))
    op.add_column("certification_runs", sa.Column("policy_version", sa.String(length=64), server_default="v1.0", nullable=False))
    op.create_foreign_key(
        "fk_certification_runs_version_id",
        "certification_runs",
        "application_versions",
        ["application_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_certification_runs_application_version_id", "certification_runs", ["application_version_id"])
    op.create_index("ix_certification_runs_submission_id", "certification_runs", ["submission_id"])

    # 3. Create certification_checks table
    op.create_table(
        "certification_checks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("certification_id", sa.String(length=64), nullable=False),
        sa.Column("check_id", sa.String(length=64), nullable=False),
        sa.Column("check_type", sa.String(length=64), nullable=False),
        sa.Column("check_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), server_default="PENDING", nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["certification_id"],
            ["certification_runs.certification_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_certification_checks_certification_id", "certification_checks", ["certification_id"])
    op.create_index("ix_certification_checks_check_id", "certification_checks", ["check_id"])
    op.create_index("ix_certification_checks_check_type", "certification_checks", ["check_type"])

    # 4. Create requirements table
    op.create_table(
        "requirements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("requirement_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("mandatory", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("policy_version", sa.String(length=64), server_default="v1.0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requirement_id"),
    )
    op.create_index("ix_requirements_requirement_id", "requirements", ["requirement_id"])
    op.create_index("ix_requirements_category", "requirements", ["category"])

    # 5. Alter certification_findings to add check_id, finding_code, updated_at
    op.add_column("certification_findings", sa.Column("check_id", sa.String(length=64), nullable=True))
    op.add_column("certification_findings", sa.Column("finding_code", sa.String(length=64), nullable=True))
    op.add_column(
        "certification_findings",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_certification_findings_check_id", "certification_findings", ["check_id"])
    op.create_index("ix_certification_findings_finding_code", "certification_findings", ["finding_code"])

    # 6. Alter evidence table
    op.add_column("evidence", sa.Column("check_id", sa.String(length=64), nullable=True))
    op.add_column("evidence", sa.Column("source_version", sa.String(length=64), nullable=True))
    op.add_column("evidence", sa.Column("source_run_id", sa.String(length=128), nullable=True))
    op.add_column("evidence", sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence", sa.Column("hash", sa.String(length=128), nullable=True))
    op.add_column("evidence", sa.Column("confidence", sa.Float(), nullable=True))
    op.create_index("ix_evidence_check_id", "evidence", ["check_id"])

    # 7. Create integration_runs table
    op.create_table(
        "integration_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("certification_id", sa.String(length=64), nullable=False),
        sa.Column("integration_run_id", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("external_application_id", sa.String(length=64), nullable=True),
        sa.Column("external_version", sa.String(length=64), nullable=True),
        sa.Column("external_run_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_metadata", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["certification_id"],
            ["certification_runs.certification_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_run_id"),
    )
    op.create_index("ix_integration_runs_certification_id", "integration_runs", ["certification_id"])
    op.create_index("ix_integration_runs_integration_run_id", "integration_runs", ["integration_run_id"])
    op.create_index("ix_integration_runs_source_system", "integration_runs", ["source_system"])
    op.create_index("ix_integration_runs_status", "integration_runs", ["status"])


def downgrade() -> None:
    op.drop_table("integration_runs")
    op.drop_index("ix_evidence_check_id", table_name="evidence")
    op.drop_column("evidence", "confidence")
    op.drop_column("evidence", "hash")
    op.drop_column("evidence", "source_timestamp")
    op.drop_column("evidence", "source_run_id")
    op.drop_column("evidence", "source_version")
    op.drop_column("evidence", "check_id")

    op.drop_index("ix_certification_findings_finding_code", table_name="certification_findings")
    op.drop_index("ix_certification_findings_check_id", table_name="certification_findings")
    op.drop_column("certification_findings", "updated_at")
    op.drop_column("certification_findings", "finding_code")
    op.drop_column("certification_findings", "check_id")

    op.drop_table("requirements")
    op.drop_table("certification_checks")

    op.drop_index("ix_certification_runs_submission_id", table_name="certification_runs")
    op.drop_index("ix_certification_runs_application_version_id", table_name="certification_runs")
    op.drop_constraint("fk_certification_runs_version_id", "certification_runs", type_="foreignkey")
    op.drop_column("certification_runs", "policy_version")
    op.drop_column("certification_runs", "trigger_type")
    op.drop_column("certification_runs", "submission_id")
    op.drop_column("certification_runs", "application_version_id")

    op.drop_table("application_versions")
