"""Add explicit procurement-category scopes for tenant isolation."""

import sqlalchemy as sa

from alembic import op

revision = "ent_003"
down_revision = "ent_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_procurement_categories",
        sa.Column("user_id", sa.String(), sa.ForeignKey("enterprise_users.user_id"), primary_key=True),
        sa.Column("category_id", sa.String(), sa.ForeignKey("procurement_categories.category_id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_te_org_dept_category",
        "task_extensions",
        ["organization_id", "department_id", "category_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_te_org_dept_category", table_name="task_extensions")
    op.drop_table("user_procurement_categories")
