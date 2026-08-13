"""Minimal procurement context persisted alongside Skyvern models."""

import datetime
import enum
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)

from skyvern.forge.sdk.db.id import generate_id
from skyvern.forge.sdk.db.models import Base


def generate_procurement_category_id() -> str:
    return f"pc_{generate_id()}"


class ProcurementCategoryModel(Base):
    __tablename__ = "procurement_categories"

    category_id = Column(String, primary_key=True, default=generate_procurement_category_id)
    organization_id = Column(String, ForeignKey("organizations.organization_id"), nullable=False, index=True)
    category_name = Column(String, nullable=False)
    category_code = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    modified_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "category_code", name="uq_org_procurement_category_code"),
        UniqueConstraint("organization_id", "category_id", name="uq_org_procurement_category_id"),
        Index("idx_procurement_category_org", "organization_id"),
    )


class UserProcurementCategoryModel(Base):
    """Explicit procurement-category read scope for a user."""

    __tablename__ = "user_procurement_categories"

    user_id = Column(String, ForeignKey("enterprise_users.user_id"), primary_key=True)
    category_id = Column(String, ForeignKey("procurement_categories.category_id"), primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


def generate_supplier_quote_id() -> str:
    return f"sq_{generate_id()}"


class HumanReviewStatus(str, enum.Enum):
    """Persisted lifecycle for a procurement human review."""

    PENDING = "pending"
    RESOLVED = "resolved"
    TERMINATED = "terminated"


class ProcurementCoordinationStateModel(Base):
    """Durable current snapshot for one procurement Planner/Coordinator task."""

    __tablename__ = "procurement_coordination_states"

    task_id = Column(String, ForeignKey("tasks.task_id"), primary_key=True)
    organization_id = Column(String, ForeignKey("organizations.organization_id"), nullable=False, index=True)
    navigation_goal = Column(Text, nullable=False)
    current_plan = Column(JSON, nullable=False)
    completed_subtask_ids = Column(JSON, nullable=False, default=list)
    total_replans = Column(Integer, nullable=False, default=0, server_default="0")
    max_replans = Column(Integer, nullable=False, default=3, server_default="3")
    status = Column(String, nullable=False, default="running", server_default="running")
    error_code = Column(String, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    modified_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_coordination_state_org_status", "organization_id", "status"),
        CheckConstraint("total_replans >= 0", name="ck_coordination_non_negative_replans"),
        CheckConstraint("max_replans >= 0", name="ck_coordination_non_negative_max_replans"),
        CheckConstraint("version >= 1", name="ck_coordination_positive_version"),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'needs_human')",
            name="ck_coordination_status",
        ),
    )


def generate_human_review_id() -> str:
    return f"phr_{generate_id()}"


class ProcurementHumanReviewModel(Base):
    """Tenant-scoped durable review created by a failed procurement extraction."""

    __tablename__ = "procurement_human_reviews"

    review_id = Column(String, primary_key=True, default=generate_human_review_id)
    task_id = Column(String, ForeignKey("tasks.task_id"), nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.organization_id"),
        nullable=False,
        index=True,
    )
    department_id = Column(String, ForeignKey("departments.department_id"), nullable=False, index=True)
    category_id = Column(String, ForeignKey("procurement_categories.category_id"), nullable=False, index=True)
    status = Column(
        String,
        nullable=False,
        default=HumanReviewStatus.PENDING.value,
        server_default=HumanReviewStatus.PENDING.value,
    )
    reason_code = Column(String, nullable=False)
    safe_error_summary = Column(Text, nullable=False)
    artifact_id = Column(String, ForeignKey("artifacts.artifact_id"), nullable=True)
    action_index = Column(Integer, nullable=False, default=0, server_default="0")
    action_type = Column(String, nullable=False)
    created_by = Column(String, ForeignKey("enterprise_users.user_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    resolved_by = Column(String, ForeignKey("enterprise_users.user_id"), nullable=True)
    resolution_action = Column(String, nullable=True)
    resolution_note = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_human_review_task", "task_id"),
        Index("idx_human_review_org_status", "organization_id", "status"),
        Index("idx_human_review_scope", "organization_id", "department_id", "category_id"),
        Index(
            "uq_human_review_pending_task",
            "task_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        CheckConstraint(
            "status IN ('pending', 'resolved', 'terminated')",
            name="ck_human_review_status",
        ),
        CheckConstraint("action_index >= 0", name="ck_human_review_non_negative_action_index"),
        CheckConstraint(
            "resolution_action IS NULL OR resolution_action IN ('skip_step', 'manual_complete', 'terminate')",
            name="ck_human_review_resolution_action",
        ),
    )


class SupplierQuoteModel(Base):
    """A normalized, tenant-scoped supplier quote for one procurement task."""

    __tablename__ = "supplier_quotes"

    quote_id = Column(String, primary_key=True, default=generate_supplier_quote_id)
    task_id = Column(String, ForeignKey("tasks.task_id"), nullable=False, index=True)
    organization_id = Column(
        String,
        ForeignKey("organizations.organization_id"),
        nullable=False,
        index=True,
    )
    department_id = Column(String, ForeignKey("departments.department_id"), nullable=False, index=True)
    category_id = Column(String, ForeignKey("procurement_categories.category_id"), nullable=False, index=True)
    supplier_id = Column(String, nullable=False)
    material_name = Column(String, nullable=False)
    quantity = Column(Numeric(18, 6), nullable=False)
    unit = Column(String, nullable=False, default="unit", server_default="unit")
    currency = Column(String, nullable=False, default="CNY", server_default="CNY")
    unit_price_cny = Column(Numeric(18, 2), nullable=False)
    freight_cny = Column(Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0")
    moq = Column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    delivery_days = Column(Integer, nullable=False)
    artifact_id = Column(String, ForeignKey("artifacts.artifact_id"), nullable=False)
    created_by = Column(String, ForeignKey("enterprise_users.user_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    modified_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_supplier_quote_org_task", "organization_id", "task_id"),
        Index("idx_supplier_quote_scope", "organization_id", "department_id", "category_id"),
        CheckConstraint("quantity > 0", name="ck_supplier_quote_positive_quantity"),
        CheckConstraint("unit = 'unit'", name="ck_supplier_quote_base_unit"),
        CheckConstraint("currency = 'CNY'", name="ck_supplier_quote_currency"),
        CheckConstraint("unit_price_cny >= 0", name="ck_supplier_quote_non_negative_unit_price"),
        CheckConstraint("freight_cny >= 0", name="ck_supplier_quote_non_negative_freight"),
        CheckConstraint("moq >= 0", name="ck_supplier_quote_non_negative_moq"),
        CheckConstraint("delivery_days >= 0", name="ck_supplier_quote_non_negative_delivery"),
    )
