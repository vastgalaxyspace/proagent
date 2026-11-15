"""add grounded amendment operations

Revision ID: 4f2b8a7d91c3
Revises: 8e4c1f7a9b02
Create Date: 2026-11-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4f2b8a7d91c3"
down_revision: Union[str, Sequence[str], None] = (
    "8e4c1f7a9b02"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tender_amendment_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_plan_id", sa.Uuid(), nullable=False),
        sa.Column(
            "logical_document_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column(
            "operation",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "target",
            sa.String(length=500),
            nullable=False,
        ),
        sa.Column(
            "previous_value_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "revised_value_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "evidence_quote",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "validation_status",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["logical_document_id"],
            ["logical_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["document_pages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_plan_id"],
            ["tender_source_plans.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tender_amendment_operations_plan_status",
        "tender_amendment_operations",
        ["source_plan_id", "validation_status"],
        unique=False,
    )
    op.create_index(
        "ix_tender_amendment_operations_target",
        "tender_amendment_operations",
        ["target"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tender_amendment_operations_source_plan_id"),
        "tender_amendment_operations",
        ["source_plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tender_amendment_operations_logical_document_id"),
        "tender_amendment_operations",
        ["logical_document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tender_amendment_operations_page_id"),
        "tender_amendment_operations",
        ["page_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tender_amendment_operations_page_id"),
        table_name="tender_amendment_operations",
    )
    op.drop_index(
        op.f(
            "ix_tender_amendment_operations_"
            "logical_document_id"
        ),
        table_name="tender_amendment_operations",
    )
    op.drop_index(
        op.f("ix_tender_amendment_operations_source_plan_id"),
        table_name="tender_amendment_operations",
    )
    op.drop_index(
        "ix_tender_amendment_operations_target",
        table_name="tender_amendment_operations",
    )
    op.drop_index(
        "ix_tender_amendment_operations_plan_status",
        table_name="tender_amendment_operations",
    )
    op.drop_table("tender_amendment_operations")
