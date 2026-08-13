"""Day 6 database approval API checks."""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from enterprise.approval import routes
from enterprise.approval.models import ApprovalRequestModel, ApprovalStatus
from enterprise.approval.routes import DecisionRequest
from enterprise.auth.schemas import DepartmentRole, UserContext
from skyvern.forge.sdk.schemas.tasks import TaskStatus


def _user(user_id: str, role: str, org_id: str = "org_1", department_id: str = "dept_1") -> UserContext:
    return UserContext(
        user_id=user_id,
        org_id=org_id,
        department_roles=[DepartmentRole(department_id=department_id, department_name="Procurement", role=role)],
        business_line_ids=[],
        procurement_category_ids=["cat_1"],
    )


def _approval(**changes) -> ApprovalRequestModel:
    values = {
        "approval_id": "apr_1",
        "task_id": "task_1",
        "organization_id": "org_1",
        "department_id": "dept_1",
        "requester_user_id": "buyer_1",
        "risk_level": "high",
        "risk_reason": "Amount requires approval",
        "approver_department_id": "dept_1",
        "status": ApprovalStatus.PENDING.value,
        "requested_at": datetime.datetime(2026, 3, 11),
        "timeout_seconds": 3600,
    }
    values.update(changes)
    return ApprovalRequestModel(**values)


class _ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Session:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    async def scalar(self, statement):
        approval_id = next(
            (value for key, value in statement.compile().params.items() if "approval_id" in key),
            None,
        )
        return self.db.approvals.get(approval_id)

    async def scalars(self, _statement):
        return _ScalarRows([
            approval for approval in self.db.approvals.values()
            if approval.status == ApprovalStatus.PENDING.value
        ])

    async def commit(self):
        self.db.commits += 1


class _Database:
    def __init__(self, approval):
        self.approvals = {approval.approval_id: approval}
        self.tasks = {
            approval.task_id: SimpleNamespace(
                task_id=approval.task_id,
                status=TaskStatus.created,
                browser_session_id=None,
            )
        }
        self.commits = 0

    def Session(self):
        return _Session(self)

    async def get_task(self, task_id, organization_id):
        return self.tasks.get(task_id)

    async def update_task(self, task_id, status, organization_id):
        self.tasks[task_id].status = status
        return self.tasks[task_id]


def _install(monkeypatch, approval=None):
    database = _Database(approval or _approval())
    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=database))
    monkeypatch.setattr(routes, "record_audit_event", AsyncMock())
    return database


@pytest.mark.asyncio
async def test_pending_list_and_approve_are_database_backed(monkeypatch):
    database = _install(monkeypatch)
    audit = routes.record_audit_event
    approver = _user("approver_1", "approver")

    pending = await routes.list_pending_approvals(approver)
    assert [approval.approval_id for approval in pending] == ["apr_1"]

    result = await routes.approve_request("apr_1", DecisionRequest(note="Approved"), approver)
    assert result.status == "approved"
    assert database.approvals["apr_1"].approver_user_id == "approver_1"
    assert database.commits == 1
    assert audit.await_args.kwargs["action_type"] == "approval_approved"

    with pytest.raises(HTTPException) as duplicate:
        await routes.approve_request("apr_1", DecisionRequest(), approver)
    assert duplicate.value.status_code == 409


@pytest.mark.asyncio
async def test_requester_cross_org_and_wrong_department_cannot_approve(monkeypatch):
    _install(monkeypatch)
    forbidden_users = (
        _user("buyer_1", "org_admin"),
        _user("approver_1", "approver", org_id="org_2"),
        _user("approver_1", "approver", department_id="dept_2"),
    )
    for user in forbidden_users:
        with pytest.raises(HTTPException) as denied:
            await routes.approve_request("apr_1", DecisionRequest(), user)
        assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_reject_cancels_task_and_cannot_continue(monkeypatch):
    database = _install(monkeypatch)
    await routes.reject_request("apr_1", DecisionRequest(note="Rejected"), _user("approver_1", "approver"))
    assert database.tasks["task_1"].status == TaskStatus.canceled

    with pytest.raises(HTTPException) as denied:
        await routes.continue_request("apr_1", BackgroundTasks(), _user("buyer_1", "operator"))
    assert denied.value.status_code == 409


@pytest.mark.asyncio
async def test_reject_snapshots_approval_before_nested_task_commit(monkeypatch):
    class ExpiringApproval:
        def __init__(self):
            self.approval_id = "apr_1"
            self.task_id = "task_1"
            self.organization_id = "org_1"
            self.department_id = "dept_1"
            self.business_line_id = None
            self.requester_user_id = "buyer_1"
            self.approver_department_id = "dept_1"
            self.status = ApprovalStatus.PENDING.value
            self.expired = False

        @property
        def task_id(self):
            if self.expired:
                raise RuntimeError("expired approval attribute")
            return self._task_id

        @task_id.setter
        def task_id(self, value):
            self._task_id = value

    approval = ExpiringApproval()
    database = _install(monkeypatch, approval)

    async def expire_on_task_update(task_id, status, organization_id):
        approval.expired = True
        database.tasks[task_id].status = status
        return database.tasks[task_id]

    database.update_task = expire_on_task_update
    result = await routes.reject_request("apr_1", DecisionRequest(note="Rejected"), _user("approver_1", "approver"))

    assert result.status == ApprovalStatus.REJECTED.value
    assert database.tasks["task_1"].status == TaskStatus.canceled


@pytest.mark.asyncio
async def test_approved_task_continues_through_skyvern_executor(monkeypatch):
    database = _install(monkeypatch)
    audit = routes.record_audit_event
    calls = []

    class Executor:
        async def execute_task(self, **kwargs):
            calls.append(kwargs)
            database.tasks[kwargs["task_id"]].status = TaskStatus.running

    monkeypatch.setattr(routes.AsyncExecutorFactory, "get_executor", staticmethod(lambda: Executor()))
    await routes.approve_request("apr_1", DecisionRequest(), _user("approver_1", "approver"))
    result = await routes.continue_request("apr_1", BackgroundTasks(), _user("buyer_1", "operator"))

    assert result.task_status == "running"
    assert calls[0]["task_id"] == "task_1"
    assert database.tasks["task_1"].status == TaskStatus.running
    assert [call.kwargs["action_type"] for call in audit.await_args_list] == [
        "approval_approved",
        "task_continued",
    ]

    with pytest.raises(HTTPException) as duplicate:
        await routes.continue_request("apr_1", BackgroundTasks(), _user("buyer_1", "operator"))
    assert duplicate.value.status_code == 409
