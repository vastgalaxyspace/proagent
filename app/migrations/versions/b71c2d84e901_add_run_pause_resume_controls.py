"""add run pause resume controls

Revision ID: b71c2d84e901
Revises: 4f2b8a7d91c3
Create Date: 2026-11-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b71c2d84e901"
down_revision: Union[str, Sequence[str], None] = "4f2b8a7d91c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "operations",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "operations",
        sa.Column("pause_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "operations",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operations", "cancel_requested_at")
    op.drop_column("operations", "pause_requested_at")
    op.drop_column("operations", "heartbeat_at")
