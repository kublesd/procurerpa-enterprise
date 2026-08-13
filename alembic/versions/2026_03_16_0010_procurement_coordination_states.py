"""Persist procurement Planner and Coordinator recovery snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "ent_010"
down_revision = "ent_009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procurement_coordination_states",
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.task_id"), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(),
            sa.ForeignKey("organizations.organization_id"),
            nullable=False,
        ),
        sa.Column("navigation_goal", sa.Text(), nullable=False),
        sa.Column("current_plan", sa.JSON(), nullable=False),
        sa.Column("completed_subtask_ids", sa.JSON(), nullable=False),
        sa.Column("total_replans", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_replans", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("total_replans >= 0", name="ck_coordination_non_negative_replans"),
        sa.CheckConstraint("max_replans >= 0", name="ck_coordination_non_negative_max_replans"),
        sa.CheckConstraint("version >= 1", name="ck_coordination_positive_version"),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'needs_human')",
            name="ck_coordination_status",
        ),
    )
    op.create_index(
        "idx_coordination_state_org_status",
        "procurement_coordination_states",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_coordination_state_org_status", table_name="procurement_coordination_states")
    op.drop_table("procurement_coordination_states")
