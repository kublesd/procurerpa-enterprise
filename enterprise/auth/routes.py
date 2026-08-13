"""Enterprise authentication API routes."""

import bcrypt
import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from skyvern.forge import app as forge_app
from skyvern.forge.sdk.db.models import OrganizationModel

from .dependencies import CurrentUser
from .models import (
    BusinessLineModel,
    DepartmentModel,
    EnterpriseUserModel,
    SpecialPermissionModel,
    UserBusinessLineModel,
    UserDepartmentRoleModel,
)
from .schemas import DepartmentRole, LoginRequest, LoginResponse

LOG = structlog.get_logger()

router = APIRouter(prefix="/enterprise/auth", tags=["Enterprise Auth"])


@router.get("/organizations")
async def list_enterprise_organizations() -> list[dict]:
    """Return organizations that have enterprise users (public, no auth required)."""
    async with forge_app.DATABASE.Session() as session:
        stmt = (
            select(
                OrganizationModel.organization_id,
                OrganizationModel.organization_name,
            )
            .where(
                OrganizationModel.organization_id.in_(
                    select(EnterpriseUserModel.organization_id).distinct()
                )
            )
            .order_by(OrganizationModel.organization_name)
        )
        result = await session.execute(stmt)
        rows = result.all()

    return [
        {"organization_id": r.organization_id, "organization_name": r.organization_name}
        for r in rows
    ]


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Authenticate an enterprise user and return a JWT with full permission context."""
    from .jwt_service import create_enterprise_token

    async with forge_app.DATABASE.Session() as session:
        # Find user by org + username
        stmt = select(EnterpriseUserModel).where(
            EnterpriseUserModel.organization_id == request.organization_id,
            EnterpriseUserModel.username == request.username,
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )

        # Verify password
        password = request.password.encode()
        if len(password) > 72 or not bcrypt.checkpw(password, user.password_hash.encode()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        # Load department roles
        dept_roles_stmt = (
            select(UserDepartmentRoleModel)
            .join(
                DepartmentModel,
                DepartmentModel.department_id == UserDepartmentRoleModel.department_id,
            )
            .where(UserDepartmentRoleModel.user_id == user.user_id)
            .where(DepartmentModel.organization_id == user.organization_id)
        )
        dept_roles_result = await session.execute(dept_roles_stmt)
        dept_role_rows = dept_roles_result.scalars().all()

        # Resolve department names inside the authenticated organization.
        department_roles = []
        for dr in dept_role_rows:
            dept_stmt = select(DepartmentModel.department_name).where(
                DepartmentModel.department_id == dr.department_id,
                DepartmentModel.organization_id == user.organization_id,
            )
            dept_result = await session.execute(dept_stmt)
            dept_name = dept_result.scalar_one_or_none() or dr.department_id
            department_roles.append(DepartmentRole(
                department_id=dr.department_id,
                department_name=dept_name,
                role=dr.role,
            ))

        # Load business line IDs
        bl_stmt = (
            select(UserBusinessLineModel.business_line_id)
            .join(
                BusinessLineModel,
                BusinessLineModel.business_line_id == UserBusinessLineModel.business_line_id,
            )
            .where(
                UserBusinessLineModel.user_id == user.user_id,
                BusinessLineModel.organization_id == user.organization_id,
            )
        )
        bl_result = await session.execute(bl_stmt)
        business_line_ids = [row for row in bl_result.scalars().all()]

        # Load special permissions
        sp_stmt = (
            select(SpecialPermissionModel.permission_type)
            .where(
                SpecialPermissionModel.user_id == user.user_id,
                SpecialPermissionModel.organization_id == user.organization_id,
            )
        )
        sp_result = await session.execute(sp_stmt)
        special_perms = set(sp_result.scalars().all())

        has_cross_org_read = "cross_org_read" in special_perms
        has_cross_org_approve = "cross_org_approve" in special_perms

    from skyvern.config import settings

    # Create enterprise JWT
    token = create_enterprise_token(
        user_id=user.user_id,
        org_id=user.organization_id,
        department_roles=department_roles,
        business_line_ids=business_line_ids,
        has_cross_org_read=has_cross_org_read,
        has_cross_org_approve=has_cross_org_approve,
    )

    LOG.info(
        "Enterprise user login",
        user_id=user.user_id,
        org_id=user.organization_id,
        roles=[f"{dr.department_id}:{dr.role}" for dr in department_roles],
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.user_id,
        display_name=user.display_name,
    )


@router.get("/me")
async def get_current_user_info(user: CurrentUser) -> dict:
    """Return the current user's trusted permission context."""
    return {
        "user_id": user.user_id,
        "org_id": user.org_id,
        "department_roles": [dr.model_dump() for dr in user.department_roles],
        "business_line_ids": user.business_line_ids,
        "procurement_category_ids": user.procurement_category_ids,
        "has_cross_org_read": user.has_cross_org_read,
        "has_cross_org_approve": user.has_cross_org_approve,
        "is_admin": user.is_org_admin,
        "is_operator": user.is_any_operator,
        "is_approver": user.is_any_approver,
    }
