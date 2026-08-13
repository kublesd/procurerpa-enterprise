"""Idempotent minimal procurement demo seed; callers own the transaction."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise.auth.models import DepartmentModel, EnterpriseUserModel, UserDepartmentRoleModel
from enterprise.procurement.models import ProcurementCategoryModel, UserProcurementCategoryModel
from skyvern.forge.sdk.db.models import OrganizationModel

DEMO_ORGANIZATION_ID = "org_procurement_demo"
DEPARTMENTS = (
    ("dept_it_procurement", "IT Procurement", "IT_PROC"),
    ("dept_services_procurement", "Services Procurement", "SERV_PROC"),
)
CATEGORIES = (
    ("pc_it", "IT Equipment", "IT"),
    ("pc_services", "Professional Services", "SERV"),
)
USERS = (
    ("eu_proc_admin", "procurement_admin", "Procurement Admin", "admin@procurement.demo"),
    ("eu_it_buyer", "it_buyer", "IT Buyer", "it.buyer@procurement.demo"),
    ("eu_services_buyer", "services_buyer", "Services Buyer", "services.buyer@procurement.demo"),
    ("eu_proc_approver", "procurement_approver", "Procurement Approver", "approver@procurement.demo"),
    ("eu_proc_viewer", "procurement_viewer", "Procurement Viewer", "viewer@procurement.demo"),
)
DEPARTMENT_ROLES = (
    ("eu_proc_admin", "dept_it_procurement", "org_admin"),
    ("eu_it_buyer", "dept_it_procurement", "operator"),
    ("eu_services_buyer", "dept_services_procurement", "operator"),
    ("eu_proc_approver", "dept_it_procurement", "approver"),
    ("eu_proc_viewer", "dept_services_procurement", "viewer"),
)
CATEGORY_GRANTS = (
    ("eu_it_buyer", "pc_it"),
    ("eu_services_buyer", "pc_services"),
    ("eu_proc_approver", "pc_it"),
    ("eu_proc_viewer", "pc_services"),
)
_DEMO_PASSWORD_HASH = "$2b$12$wBw3SCe72lwNbxfHlbzKfeLfkv7CgkBr4m9YPNFpUQpf/DU14zf/C"


async def seed_procurement_data(session: AsyncSession) -> dict[str, int]:
    if await session.get(OrganizationModel, DEMO_ORGANIZATION_ID) is None:
        session.add(OrganizationModel(organization_id=DEMO_ORGANIZATION_ID, organization_name="ProcureRPA Demo"))
    for department_id, department_name, department_code in DEPARTMENTS:
        if await session.scalar(select(DepartmentModel.department_id).where(DepartmentModel.department_id == department_id)) is None:
            session.add(DepartmentModel(department_id=department_id, organization_id=DEMO_ORGANIZATION_ID, department_name=department_name, department_code=department_code))
    for category_id, category_name, category_code in CATEGORIES:
        if await session.scalar(select(ProcurementCategoryModel.category_id).where(ProcurementCategoryModel.category_id == category_id)) is None:
            session.add(ProcurementCategoryModel(category_id=category_id, organization_id=DEMO_ORGANIZATION_ID, category_name=category_name, category_code=category_code))
    for user_id, username, display_name, email in USERS:
        if await session.scalar(select(EnterpriseUserModel.user_id).where(EnterpriseUserModel.user_id == user_id)) is None:
            session.add(EnterpriseUserModel(user_id=user_id, organization_id=DEMO_ORGANIZATION_ID, username=username, password_hash=_DEMO_PASSWORD_HASH, display_name=display_name, email=email))
    for user_id, department_id, role in DEPARTMENT_ROLES:
        if await session.scalar(select(UserDepartmentRoleModel.user_id).where(UserDepartmentRoleModel.user_id == user_id, UserDepartmentRoleModel.department_id == department_id)) is None:
            session.add(UserDepartmentRoleModel(user_id=user_id, department_id=department_id, role=role))
    for user_id, category_id in CATEGORY_GRANTS:
        if await session.scalar(select(UserProcurementCategoryModel.user_id).where(UserProcurementCategoryModel.user_id == user_id, UserProcurementCategoryModel.category_id == category_id)) is None:
            session.add(UserProcurementCategoryModel(user_id=user_id, category_id=category_id))
    return {
        "organizations": 1,
        "departments": len(DEPARTMENTS),
        "categories": len(CATEGORIES),
        "users": len(USERS),
        "department_roles": len(DEPARTMENT_ROLES),
        "category_grants": len(CATEGORY_GRANTS),
    }
