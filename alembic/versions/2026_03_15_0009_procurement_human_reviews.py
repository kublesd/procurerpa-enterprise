"""Persist procurement human reviews created by failed extraction."""

import sqlalchemy as sa

from alembic import op

revision = "ent_009"
down_revision = "ent_008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procurement_human_reviews",
        sa.Column("review_id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.organization_id"), nullable=False),
        sa.Column("department_id", sa.String(), sa.ForeignKey("departments.department_id"), nullable=False),
        sa.Column("category_id", sa.String(), sa.ForeignKey("procurement_categories.category_id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reason_code", sa.String(), nullable=False),
        sa.Column("safe_error_summary", sa.Text(), nullable=False),
        sa.Column("artifact_id", sa.String(), sa.ForeignKey("artifacts.artifact_id"), nullable=True),
        sa.Column("action_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("enterprise_users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_by", sa.String(), sa.ForeignKey("enterprise_users.user_id"), nullable=True),
        sa.Column("resolution_action", sa.String(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'resolved', 'terminated')",
            name="ck_human_review_status",
        ),
        sa.CheckConstraint("action_index >= 0", name="ck_human_review_non_negative_action_index"),
        sa.CheckConstraint(
            "resolution_action IS NULL OR resolution_action IN ('skip_step', 'manual_complete', 'terminate')",
            name="ck_human_review_resolution_action",
        ),
    )
    op.create_index("idx_human_review_task", "procurement_human_reviews", ["task_id"])
    op.create_index(
        "idx_human_review_org_status",
        "procurement_human_reviews",
        ["organization_id", "status"],
    )
    op.create_index(
        "idx_human_review_scope",
        "procurement_human_reviews",
        ["organization_id", "department_id", "category_id"],
    )
    op.create_index(
        "uq_human_review_pending_task",
        "procurement_human_reviews",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_human_review_pending_task", table_name="procurement_human_reviews")
    op.drop_index("idx_human_review_scope", table_name="procurement_human_reviews")
    op.drop_index("idx_human_review_org_status", table_name="procurement_human_reviews")
    op.drop_index("idx_human_review_task", table_name="procurement_human_reviews")
    op.drop_table("procurement_human_reviews")
