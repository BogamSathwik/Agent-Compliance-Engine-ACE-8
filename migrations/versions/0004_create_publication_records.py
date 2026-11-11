"""Create publication_records table for AgentGen Pro integration.

Revision ID: 0004_create_publication_records
Revises: 0003_seed_17_document_requirements
Create Date: 2026-10-28 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004_create_publication_records"
down_revision: Union[str, None] = "0003_seed_17_document_requirements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "publication_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("publication_id", sa.String(length=64), nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("application_version", sa.String(length=64), nullable=False),
        sa.Column("application_version_id", sa.Integer(), nullable=True),
        sa.Column("certification_id", sa.String(length=64), nullable=False),
        sa.Column("submission_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=64), server_default="CERTIFIED", nullable=False),
        sa.Column("external_publication_id", sa.String(length=128), nullable=True),
        sa.Column("external_status", sa.String(length=64), nullable=True),
        sa.Column("external_confirmation", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=64), server_default="operator", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
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
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.application_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["application_version_id"],
            ["application_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["certification_id"],
            ["certification_runs.certification_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("publication_id"),
    )
    op.create_index("ix_publication_records_publication_id", "publication_records", ["publication_id"])
    op.create_index("ix_publication_records_application_id", "publication_records", ["application_id"])
    op.create_index("ix_publication_records_application_version", "publication_records", ["application_version"])
    op.create_index("ix_publication_records_application_version_id", "publication_records", ["application_version_id"])
    op.create_index("ix_publication_records_certification_id", "publication_records", ["certification_id"])
    op.create_index("ix_publication_records_submission_id", "publication_records", ["submission_id"])
    op.create_index("ix_publication_records_status", "publication_records", ["status"])
    op.create_index("ix_publication_records_external_publication_id", "publication_records", ["external_publication_id"])


def downgrade() -> None:
    op.drop_index("ix_publication_records_external_publication_id", table_name="publication_records")
    op.drop_index("ix_publication_records_status", table_name="publication_records")
    op.drop_index("ix_publication_records_submission_id", table_name="publication_records")
    op.drop_index("ix_publication_records_certification_id", table_name="publication_records")
    op.drop_index("ix_publication_records_application_version_id", table_name="publication_records")
    op.drop_index("ix_publication_records_application_version", table_name="publication_records")
    op.drop_index("ix_publication_records_application_id", table_name="publication_records")
    op.drop_index("ix_publication_records_publication_id", table_name="publication_records")
    op.drop_table("publication_records")
