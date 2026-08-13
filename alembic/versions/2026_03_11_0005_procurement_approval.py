"""Add database-backed single-level procurement approvals."""

import sqlalchemy as sa

from alembic import op

revision = "ent_005"
down_revision = "ent_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("approval_id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.task_id"), nullable=False, unique=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.organization_id"), nullable=False),
        sa.Column("department_id", sa.String(), sa.ForeignKey("departments.department_id"), nullable=False),
        sa.Column("business_line_id", sa.String(), sa.ForeignKey("business_lines.business_line_id"), nullable=True),
        sa.Column("risk_level", sa.String(), nullable=False),
        sa.Column("risk_reason", sa.Text(), nullable=False),
        sa.Column("operation_description", sa.Text(), nullable=True),
        sa.Column("screenshot_path", sa.String(), nullable=True),
        sa.Column("requester_user_id", sa.String(), sa.ForeignKey("enterprise_users.user_id"), nullable=False),
        sa.Column("approver_department_id", sa.String(), sa.ForeignKey("departments.department_id"), nullable=False),
        sa.Column("approver_role", sa.String(), nullable=False, server_default="approver"),
        sa.Column("notify_department_ids", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("approver_user_id", sa.String(), sa.ForeignKey("enterprise_users.user_id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.CheckConstraint("risk_level IN ('high', 'critical')", name="ck_approval_risk_level"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'timeout')", name="ck_valid_approval_status"),
        sa.CheckConstraint("timeout_seconds > 0", name="ck_positive_timeout"),
    )
    op.create_index("idx_apr_org_status", "approval_requests", ["organization_id", "status"])
    op.create_index("idx_apr_dept_status", "approval_requests", ["approver_department_id", "status"])


def downgrade() -> None:
    op.drop_table("approval_requests")
