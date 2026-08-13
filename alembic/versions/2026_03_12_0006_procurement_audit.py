"""Persist scoped procurement audit events."""

import sqlalchemy as sa

from alembic import op

revision = "ent_006"
down_revision = "ent_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("audit_log_id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.organization_id"), nullable=False),
        sa.Column("department_id", sa.String(), sa.ForeignKey("departments.department_id"), nullable=False),
        sa.Column("business_line_id", sa.String(), sa.ForeignKey("business_lines.business_line_id"), nullable=True),
        sa.Column("business_object_type", sa.String(), nullable=True),
        sa.Column("business_object_id", sa.String(), nullable=True),
        sa.Column("action_index", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("target_element", sa.Text(), nullable=True),
        sa.Column("input_value", sa.Text(), nullable=True),
        sa.Column("input_value_raw_hash", sa.String(), nullable=True),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("screenshot_before_key", sa.String(), nullable=True),
        sa.Column("screenshot_after_key", sa.String(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("executor", sa.String(), nullable=False),
        sa.Column("execution_result", sa.String(), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("has_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approval_id", sa.String(), nullable=True),
        sa.Column("approver_user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("action_index >= 0", name="ck_non_negative_action_index"),
    )
    op.create_index("ix_audit_logs_task_id", "audit_logs", ["task_id"])
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("idx_aud_task_action", "audit_logs", ["task_id", "action_index"])
    op.create_index("idx_aud_org_time", "audit_logs", ["organization_id", "created_at"])
    op.create_index("idx_aud_dept_time", "audit_logs", ["department_id", "created_at"])
    op.create_index("idx_aud_business_object", "audit_logs", ["business_object_type", "business_object_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
