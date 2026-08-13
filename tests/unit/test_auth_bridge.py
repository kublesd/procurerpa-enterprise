"""Tests for the enterprise JWT bridge into native Skyvern routes."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from enterprise.auth import bridge
from enterprise.auth.jwt_service import create_enterprise_token
from enterprise.auth.schemas import DepartmentRole, UserContext
from skyvern.forge.sdk.services import org_auth_service


def _token(role: str = "super_admin", org_id: str = "org-token") -> str:
    return create_enterprise_token(
        user_id="user-test",
        org_id=org_id,
        department_roles=[DepartmentRole(department_id="dept-test", department_name="Test", role=role)],
        business_line_ids=[],
    )


def _user(role: str = "operator", org_id: str = "org-server") -> UserContext:
    return UserContext(
        user_id="user-test",
        org_id=org_id,
        department_roles=[DepartmentRole(department_id="dept-test", department_name="Test", role=role)],
        business_line_ids=[],
    )


@pytest.mark.asyncio
async def test_native_org_dependency_rejects_viewer_from_trusted_roles(monkeypatch) -> None:
    async def load_user(_user_id: str) -> UserContext:
        return _user("viewer")

    monkeypatch.setattr(bridge, "_load_current_user", load_user)
    monkeypatch.setattr(
        org_auth_service,
        "app",
        SimpleNamespace(authentication_function=bridge.authenticate_enterprise_token),
    )

    with pytest.raises(HTTPException) as exc_info:
        await org_auth_service._authenticate_helper(f"Bearer {_token()}")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_native_org_dependency_rejects_disabled_user(monkeypatch) -> None:
    async def load_user(_user_id: str) -> None:
        return None

    monkeypatch.setattr(bridge, "_load_current_user", load_user)
    monkeypatch.setattr(
        org_auth_service,
        "app",
        SimpleNamespace(authentication_function=bridge.authenticate_enterprise_token),
    )

    with pytest.raises(HTTPException) as exc_info:
        await org_auth_service._authenticate_helper(f"Bearer {_token()}")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_native_org_dependency_rejects_restricted_operator(monkeypatch) -> None:
    async def load_user(_user_id: str) -> UserContext:
        return _user()

    monkeypatch.setattr(bridge, "_load_current_user", load_user)
    monkeypatch.setattr(
        org_auth_service,
        "app",
        SimpleNamespace(authentication_function=bridge.authenticate_enterprise_token),
    )

    with pytest.raises(HTTPException) as exc_info:
        await org_auth_service._authenticate_helper(f"Bearer {_token()}")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_native_org_dependency_uses_trusted_admin_and_organization(monkeypatch) -> None:
    async def load_user(_user_id: str) -> UserContext:
        return _user("org_admin")

    async def get_organization(organization_id: str):
        assert organization_id == "org-server"
        return SimpleNamespace(organization_id=organization_id, organization_name="Server organization")

    monkeypatch.setattr(bridge, "_load_current_user", load_user)
    monkeypatch.setattr(bridge, "forge_app", SimpleNamespace(DATABASE=SimpleNamespace(get_organization=get_organization)))
    monkeypatch.setattr(
        org_auth_service,
        "app",
        SimpleNamespace(authentication_function=bridge.authenticate_enterprise_token),
    )

    organization = await org_auth_service._authenticate_helper(f"Bearer {_token(org_id='org-token')}")
    assert organization.organization_id == "org-server"
