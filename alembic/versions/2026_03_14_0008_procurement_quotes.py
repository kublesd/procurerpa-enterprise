"""Persist normalized, tenant-scoped supplier quotes."""

import sqlalchemy as sa

from alembic import op

revision = "ent_008"
down_revision = "ent_007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_quotes",
        sa.Column("quote_id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.organization_id"), nullable=False),
        sa.Column("department_id", sa.String(), sa.ForeignKey("departments.department_id"), nullable=False),
        sa.Column("category_id", sa.String(), sa.ForeignKey("procurement_categories.category_id"), nullable=False),
        sa.Column("supplier_id", sa.String(), nullable=False),
        sa.Column("material_name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(), nullable=False, server_default="unit"),
        sa.Column("currency", sa.String(), nullable=False, server_default="CNY"),
        sa.Column("unit_price_cny", sa.Numeric(18, 2), nullable=False),
        sa.Column("freight_cny", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("moq", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("delivery_days", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.String(), sa.ForeignKey("artifacts.artifact_id"), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("enterprise_users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity > 0", name="ck_supplier_quote_positive_quantity"),
        sa.CheckConstraint("unit = 'unit'", name="ck_supplier_quote_base_unit"),
        sa.CheckConstraint("currency = 'CNY'", name="ck_supplier_quote_currency"),
        sa.CheckConstraint("unit_price_cny >= 0", name="ck_supplier_quote_non_negative_unit_price"),
        sa.CheckConstraint("freight_cny >= 0", name="ck_supplier_quote_non_negative_freight"),
        sa.CheckConstraint("moq >= 0", name="ck_supplier_quote_non_negative_moq"),
        sa.CheckConstraint("delivery_days >= 0", name="ck_supplier_quote_non_negative_delivery"),
    )
    op.create_index("idx_supplier_quote_org_task", "supplier_quotes", ["organization_id", "task_id"])
    op.create_index(
        "idx_supplier_quote_scope",
        "supplier_quotes",
        ["organization_id", "department_id", "category_id"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_supplier_quote_context() RETURNS TRIGGER AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM tasks
                WHERE task_id = NEW.task_id AND organization_id = NEW.organization_id
            ) THEN
                RAISE EXCEPTION 'supplier quote task organization mismatch';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM task_extensions
                WHERE task_id = NEW.task_id
                  AND organization_id = NEW.organization_id
                  AND department_id = NEW.department_id
                  AND category_id = NEW.category_id
            ) THEN
                RAISE EXCEPTION 'supplier quote procurement context mismatch';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM artifacts
                WHERE artifact_id = NEW.artifact_id AND organization_id = NEW.organization_id
            ) THEN
                RAISE EXCEPTION 'supplier quote artifact organization mismatch';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_check_supplier_quote_context
        BEFORE INSERT OR UPDATE ON supplier_quotes
        FOR EACH ROW EXECUTE FUNCTION check_supplier_quote_context();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_check_supplier_quote_context ON supplier_quotes")
    op.execute("DROP FUNCTION IF EXISTS check_supplier_quote_context()")
    op.drop_index("idx_supplier_quote_scope", table_name="supplier_quotes")
    op.drop_index("idx_supplier_quote_org_task", table_name="supplier_quotes")
    op.drop_table("supplier_quotes")
