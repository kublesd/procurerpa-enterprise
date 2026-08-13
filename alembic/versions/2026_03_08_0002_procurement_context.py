"""Add procurement categories and enforce procurement task context.

Revision ID: ent_002
Revises: ent_001
"""

import sqlalchemy as sa

from alembic import op

revision = "ent_002"
down_revision = "ent_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_org_department_id", "departments", ["organization_id", "department_id"])
    op.create_table(
        "procurement_categories",
        sa.Column("category_id", sa.String(), primary_key=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.organization_id"), nullable=False),
        sa.Column("category_name", sa.String(), nullable=False),
        sa.Column("category_code", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("modified_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("organization_id", "category_code", name="uq_org_procurement_category_code"),
        sa.UniqueConstraint("organization_id", "category_id", name="uq_org_procurement_category_id"),
    )
    op.create_index("idx_procurement_category_org", "procurement_categories", ["organization_id"])
    op.add_column("task_extensions", sa.Column("category_id", sa.String(), nullable=True))
    op.create_index("idx_te_category", "task_extensions", ["category_id"])
    op.create_foreign_key("fk_task_extensions_task", "task_extensions", "tasks", ["task_id"], ["task_id"])
    op.create_foreign_key("fk_task_extensions_category", "task_extensions", "procurement_categories", ["category_id"], ["category_id"])
    op.execute("""
        CREATE OR REPLACE FUNCTION check_procurement_task_context() RETURNS TRIGGER AS $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM tasks WHERE task_id = NEW.task_id AND organization_id = NEW.organization_id) THEN RAISE EXCEPTION 'task organization mismatch'; END IF;
            IF NOT EXISTS (SELECT 1 FROM departments WHERE department_id = NEW.department_id AND organization_id = NEW.organization_id) THEN RAISE EXCEPTION 'department organization mismatch'; END IF;
            IF NEW.category_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM procurement_categories WHERE category_id = NEW.category_id AND organization_id = NEW.organization_id) THEN RAISE EXCEPTION 'category organization mismatch'; END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
    """)
    op.execute("CREATE TRIGGER trg_check_procurement_task_context BEFORE INSERT OR UPDATE ON task_extensions FOR EACH ROW EXECUTE FUNCTION check_procurement_task_context();")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_check_procurement_task_context ON task_extensions")
    op.execute("DROP FUNCTION IF EXISTS check_procurement_task_context()")
    op.drop_constraint("fk_task_extensions_category", "task_extensions", type_="foreignkey")
    op.drop_constraint("fk_task_extensions_task", "task_extensions", type_="foreignkey")
    op.drop_index("idx_te_category", table_name="task_extensions")
    op.drop_column("task_extensions", "category_id")
    op.drop_index("idx_procurement_category_org", table_name="procurement_categories")
    op.drop_table("procurement_categories")
    op.drop_constraint("uq_org_department_id", "departments", type_="unique")
