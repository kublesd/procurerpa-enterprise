"""Core permission resolver for multi-dimensional RBAC.

Given a user context and a target resource, resolves the user's
effective permission level: none, read, operate, or approve.
"""

import enum

from .schemas import UserContext


class PermissionLevel(str, enum.Enum):
    """Effective permission level on a resource."""

    NONE = "none"
    READ = "read"
    OPERATE = "operate"
    APPROVE = "approve"


# Role -> base permission level mapping
_ROLE_PERMISSION_MAP = {
    "super_admin": PermissionLevel.APPROVE,
    "org_admin": PermissionLevel.APPROVE,
    "approver": PermissionLevel.APPROVE,
    "operator": PermissionLevel.OPERATE,
    "viewer": PermissionLevel.READ,
}


def _higher_permission(a: PermissionLevel, b: PermissionLevel) -> PermissionLevel:
    """Return the higher of two permission levels."""
    order = [PermissionLevel.NONE, PermissionLevel.READ, PermissionLevel.OPERATE, PermissionLevel.APPROVE]
    return a if order.index(a) >= order.index(b) else b


def resolve_permission(
    user: UserContext,
    resource_org_id: str,
    resource_department_id: str,
    resource_business_line_id: str | None = None,
    resource_category_id: str | None = None,
    *,
    procurement_category_id: str | None = None,
) -> PermissionLevel:
    """Resolve the effective permission level for a user on a specific resource.

    Decision logic (evaluated in order, highest permission wins):

    1. If user is super_admin or org_admin in same org -> full access (APPROVE)
    2. If resource is in user's department -> use department role
    3. If resource is in user's procurement category -> use department role (highest)
    4. ``business_line`` remains a compatibility path for legacy callers
    5. If user has cross_org_read special permission -> READ
       If user has cross_org_approve special permission -> APPROVE
    6. Otherwise -> NONE
    """
    # Different organization = no access (unless cross-org permissions)
    if user.org_id != resource_org_id:
        return PermissionLevel.NONE

    resource_category_id = resource_category_id or procurement_category_id
    category_scope_matches = resource_category_id is None or user.has_procurement_category(resource_category_id)

    effective = PermissionLevel.NONE

    # Check each department role
    for dr in user.department_roles:
        role_perm = _ROLE_PERMISSION_MAP.get(dr.role, PermissionLevel.NONE)

        # super_admin / org_admin: full access within organization
        if dr.role in ("super_admin", "org_admin"):
            return PermissionLevel.APPROVE

        if not category_scope_matches:
            continue

        # Resource is in user's department
        if dr.department_id == resource_department_id:
            effective = _higher_permission(effective, role_perm)

        # Legacy cross-department access via business line.
        elif resource_category_id is None and resource_business_line_id and user.has_business_line(resource_business_line_id):
            effective = _higher_permission(effective, role_perm)

    # Special cross-org permissions (risk management, compliance)
    if user.has_cross_org_approve:
        effective = _higher_permission(effective, PermissionLevel.APPROVE)
    elif user.has_cross_org_read:
        effective = _higher_permission(effective, PermissionLevel.READ)

    return effective
