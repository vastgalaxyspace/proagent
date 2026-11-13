"""add tender review handoff

Revision ID: 8e4c1f7a9b02
Revises: 1c22228c7aff
Create Date: 2026-11-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8e4c1f7a9b02"
down_revision: Union[str, Sequence[str], None] = "1c22228c7aff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tender_review_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("finalization_run_id", sa.Uuid(), nullable=False),
        sa.Column("tender_version_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("package_json", postgresql.JSONB(), nullable=False),
        sa.Column("original_profile_json", postgresql.JSONB(), nullable=False),
        sa.Column("corrected_profile_json", postgresql.JSONB(), nullable=True),
        sa.Column("decision", sa.String(length=50), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("reviewer_user_id", sa.String(length=100), nullable=True),
        sa.Column("correction_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["finalization_run_id"], ["tender_finalization_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tender_version_id"], ["tender_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finalization_run_id", name="uq_tender_review_sessions_finalization"),
        sa.UniqueConstraint("thread_id", name="uq_tender_review_sessions_thread"),
    )
    op.create_index("ix_tender_review_sessions_tenant_id", "tender_review_sessions", ["tenant_id"])
    op.create_index("ix_tender_review_sessions_finalization_run_id", "tender_review_sessions", ["finalization_run_id"])
    op.create_index("ix_tender_review_sessions_tender_version_id", "tender_review_sessions", ["tender_version_id"])
    op.create_index("ix_tender_review_sessions_tenant_status", "tender_review_sessions", ["tenant_id", "status"])

    op.create_table(
        "tender_review_corrections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_session_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_key", sa.String(length=255), nullable=False),
        sa.Column("patch_json", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("applied", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["review_session_id"], ["tender_review_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_session_id", "ordinal", name="uq_tender_review_corrections_ordinal"),
    )
    op.create_index("ix_tender_review_corrections_review_session_id", "tender_review_corrections", ["review_session_id"])


def downgrade() -> None:
    op.drop_index("ix_tender_review_corrections_review_session_id", table_name="tender_review_corrections")
    op.drop_table("tender_review_corrections")
    op.drop_index("ix_tender_review_sessions_tenant_status", table_name="tender_review_sessions")
    op.drop_index("ix_tender_review_sessions_tender_version_id", table_name="tender_review_sessions")
    op.drop_index("ix_tender_review_sessions_finalization_run_id", table_name="tender_review_sessions")
    op.drop_index("ix_tender_review_sessions_tenant_id", table_name="tender_review_sessions")
    op.drop_table("tender_review_sessions")
