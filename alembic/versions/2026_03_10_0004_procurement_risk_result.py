"""Persist procurement risk reasons and deterministic evidence."""

import sqlalchemy as sa

from alembic import op

revision = "ent_004"
down_revision = "ent_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_extensions", sa.Column("risk_reason", sa.Text(), nullable=True))
    op.add_column("task_extensions", sa.Column("risk_result", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("task_extensions", "risk_result")
    op.drop_column("task_extensions", "risk_reason")
