"""Day 8 procurement audit, sanitization, and MinIO checks."""

import io
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect
from starlette.datastructures import UploadFile

from enterprise.audit import routes
from enterprise.audit.logger import write_audit_log
from enterprise.audit.models import ActionType, AuditLogModel
from enterprise.audit.sanitizer import sanitize_input, sanitize_payload
from enterprise.audit.storage import (
    generate_object_key,
    generate_quote_object_key,
    get_bucket_name,
    get_presigned_url,
    split_minio_uri,
    upload_file,
)
from enterprise.auth.schemas import DepartmentRole, UserContext


def _user(role: str = "viewer", org_id: str = "org_1") -> UserContext:
    return UserContext(
        user_id="user_1",
        org_id=org_id,
        department_roles=[DepartmentRole(department_id="dept_1", department_name="采购部", role=role)],
        business_line_ids=[],
        procurement_category_ids=["cat_1"],
    )


def _mixed_role_user() -> UserContext:
    return UserContext(
        user_id="user_1",
        org_id="org_1",
        department_roles=[
            DepartmentRole(department_id="dept_view", department_name="审计部", role="viewer"),
            DepartmentRole(department_id="dept_operate", department_name="采购部", role="operator"),
        ],
        business_line_ids=[],
        procurement_category_ids=["cat_1"],
    )


def test_audit_model_supports_procurement_business_objects() -> None:
    columns = {column.name for column in inspect(AuditLogModel).columns}
    assert {"business_object_type", "business_object_id"} <= columns
    assert ActionType.RISK_ASSESSED.value == "risk_assessed"
    assert ActionType.QUOTE_FILE_UPLOADED.value == "quote_file_uploaded"


def test_recursive_sanitizer_removes_procurement_secrets() -> None:
    raw = {
        "password": "demo-password",
        "supplier": {
            "bank_account": "6222021234567890123",
            "selected_quote_cny": "12345.67",
            "contacts": ["phone: 13812345678", "token=demo-token"],
        },
        "total_amount_cny": "50000",
    }
    sanitized = json.dumps(sanitize_payload(raw), ensure_ascii=False)

    for secret in ("demo-password", "6222021234567890123", "12345.67", "13812345678", "demo-token"):
        assert secret not in sanitized
    assert "50000" in sanitized
    assert "90123"[-4:] in sanitized


def test_free_text_sanitizer_masks_authorization_and_unlabelled_supplier_account() -> None:
    bearer = "eyJhbGciOiJIUzI1NiJ9.payload.signature"
    account = "6222021234567890123"
    sanitized = sanitize_input(f"Authorization: Bearer {bearer}; supplier account {account}")

    assert bearer not in sanitized
    assert account not in sanitized
    assert "0123" in sanitized

    signed_url = "https://minio.example/quote.pdf?X-Amz-Signature=secret-signature&token=secret-token"
    sanitized_url = sanitize_input(signed_url)
    assert "secret-signature" not in sanitized_url
    assert "secret-token" not in sanitized_url
    assert sanitized_url.endswith("?[redacted]")


@pytest.mark.asyncio
async def test_writer_persists_only_sanitized_details_and_fails_open() -> None:
    class Session:
        def __init__(self):
            self.saved = []
            self.commits = 0
            self.rollbacks = 0

        def add(self, entry):
            self.saved.append(entry)

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    session = Session()
    bearer = "test.header.payload.signature"
    account = "6222021234567890123"
    entry = await write_audit_log(
        session,
        task_id="task_1",
        org_id="org_1",
        department_id="dept_1",
        action_index=0,
        action_type=ActionType.RISK_ASSESSED.value,
        executor="user_1",
        business_object_type="procurement_task",
        business_object_id="task_1",
        input_value={
            "password": "demo-password",
            "supplier_bank_account": "6222021234567890",
            "decision_note": f"Authorization: Bearer {bearer}; supplier account {account}",
        },
        error_message="token=demo-token",
    )

    assert entry is session.saved[0]
    assert session.commits == 1
    assert "demo-password" not in entry.input_value
    assert "6222021234567890" not in entry.input_value
    assert bearer not in entry.input_value
    assert account not in entry.input_value
    assert "demo-token" not in entry.error_message

    async def fail_commit():
        raise RuntimeError("database unavailable")

    session.commit = fail_commit
    assert await write_audit_log(
        session,
        task_id="task_1",
        org_id="org_1",
        department_id="dept_1",
        action_index=1,
        action_type="test",
        executor="user_1",
    ) is None
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_minio_helpers_upload_and_presign_without_blocking_client_contract() -> None:
    client = MagicMock()
    client.bucket_exists.return_value = False
    client.presigned_get_object.return_value = "https://minio.example/signed"
    bucket = get_bucket_name(datetime(2026, 3, 1))
    key = generate_quote_object_key("org_1", "task_1", "../../报价.pdf")

    uri = await upload_file(client, bucket, key, b"%PDF-demo", "application/pdf")
    url = await get_presigned_url(client, bucket, key)

    assert bucket == "procurerpa-audit-202603"
    assert key.startswith("quotes/org_1/task_1/")
    assert ".." not in key
    assert split_minio_uri(uri) == (bucket, key)
    assert url.endswith("/signed")
    client.make_bucket.assert_called_once_with(bucket)
    client.put_object.assert_called_once()


def test_screenshot_key_rejects_invalid_phase() -> None:
    with pytest.raises(ValueError):
        generate_object_key("org_1", "task_1", 0, "during")


@pytest.mark.asyncio
async def test_audit_query_is_database_backed_and_scoped(monkeypatch) -> None:
    viewer_log = AuditLogModel(
        audit_log_id="aud_1",
        task_id="task_1",
        organization_id="org_1",
        department_id="dept_view",
        action_index=0,
        action_type="risk_assessed",
        executor="user_1",
        execution_result="success",
        has_approval=False,
        created_at=datetime(2026, 3, 12),
    )
    operator_log = AuditLogModel(
        audit_log_id="aud_2",
        task_id="task_2",
        organization_id="org_1",
        department_id="dept_operate",
        action_index=0,
        action_type="risk_assessed",
        executor="user_1",
        execution_result="success",
        has_approval=False,
        created_at=datetime(2026, 3, 12),
    )
    statements = []

    class ScalarRows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        @staticmethod
        def visible(statement):
            params = statement.compile().params.values()
            allowed = next((value for value in params if value == ["dept_view"]), [])
            return [log for log in (viewer_log, operator_log) if log.department_id in allowed]

        async def scalar(self, statement):
            statements.append(statement)
            return len(self.visible(statement))

        async def scalars(self, statement):
            statements.append(statement)
            return ScalarRows(self.visible(statement))

    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=SimpleNamespace(Session=lambda: Session())))
    result = await routes.query_audit_logs(
        user=_mixed_role_user(),
        task_id=None,
        action_type=None,
        executor=None,
        business_object_type=None,
        business_object_id=None,
        start_time=None,
        end_time=None,
        page=1,
        page_size=20,
    )

    params = {}
    for statement in statements:
        params.update(statement.compile().params)
    assert result.total == 1
    assert result.items[0].task_id == "task_1"
    assert "org_1" in params.values()
    assert ["dept_view"] in params.values()
    assert ["dept_view", "dept_operate"] not in params.values()

    with pytest.raises(HTTPException) as denied:
        await routes.query_audit_logs(
            user=_user("operator"),
            task_id=None,
            action_type=None,
            executor=None,
            business_object_type=None,
            business_object_id=None,
            start_time=None,
            end_time=None,
            page=1,
            page_size=20,
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_quote_pdf_upload_uses_minio_artifact_and_audit(monkeypatch) -> None:
    extension = SimpleNamespace(department_id="dept_operate", business_line_id=None)
    statements = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def scalar(self, statement):
            statements.append(statement)
            return extension

    database = SimpleNamespace(Session=lambda: Session(), create_artifact=AsyncMock())
    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=database))
    monkeypatch.setattr(routes, "get_minio_client", lambda: MagicMock())
    monkeypatch.setattr(routes, "upload_file", AsyncMock(return_value="minio://bucket/quotes/file.pdf"))
    monkeypatch.setattr(routes, "get_presigned_url", AsyncMock(return_value="https://minio.example/signed"))
    audit = AsyncMock()
    monkeypatch.setattr(routes, "record_audit_event", audit)

    response = await routes.upload_quote_file(
        "task_1",
        UploadFile(filename="quote.pdf", file=io.BytesIO(b"%PDF-demo"), headers={"content-type": "application/pdf"}),
        _mixed_role_user(),
    )

    assert response.task_id == "task_1"
    assert response.object_uri.startswith("minio://")
    database.create_artifact.assert_awaited_once()
    assert audit.await_args.kwargs["action_type"] == "quote_file_uploaded"
    params = statements[0].compile().params.values()
    assert ["dept_operate"] in params
    assert "dept_view" not in params


@pytest.mark.asyncio
async def test_mixed_role_user_cannot_upload_to_viewer_only_department(monkeypatch) -> None:
    extension = SimpleNamespace(department_id="dept_view")

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def scalar(self, statement):
            values = statement.compile().params.values()
            allowed = next((value for value in values if value == ["dept_operate"]), [])
            return extension if extension.department_id in allowed else None

    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=SimpleNamespace(Session=lambda: Session())))

    with pytest.raises(HTTPException) as denied:
        await routes.upload_quote_file(
            "task_view",
            UploadFile(filename="quote.pdf", file=io.BytesIO(b"%PDF-demo"), headers={"content-type": "application/pdf"}),
            _mixed_role_user(),
        )
    assert denied.value.status_code == 404


@pytest.mark.asyncio
async def test_quote_upload_rejects_invalid_mime_and_oversize(monkeypatch) -> None:
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def scalar(self, _statement):
            return SimpleNamespace(department_id="dept_1", business_line_id=None)

    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=SimpleNamespace(Session=lambda: Session())))
    with pytest.raises(HTTPException) as invalid:
        await routes.upload_quote_file(
            "task_1",
            UploadFile(filename="quote.txt", file=io.BytesIO(b"not-pdf"), headers={"content-type": "text/plain"}),
            _user("operator"),
        )
    assert invalid.value.status_code == 415

    monkeypatch.setattr(routes.settings, "MAX_UPLOAD_FILE_SIZE", 5)
    with pytest.raises(HTTPException) as large:
        await routes.upload_quote_file(
            "task_1",
            UploadFile(filename="quote.pdf", file=io.BytesIO(b"%PDF-too-large"), headers={"content-type": "application/pdf"}),
            _user("operator"),
        )
    assert large.value.status_code == 413


@pytest.mark.asyncio
async def test_quote_upload_reports_minio_failure_without_writing_artifact(monkeypatch) -> None:
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def scalar(self, _statement):
            return SimpleNamespace(department_id="dept_1", business_line_id=None)

    database = SimpleNamespace(Session=lambda: Session(), create_artifact=AsyncMock())
    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=database))
    monkeypatch.setattr(routes, "get_minio_client", lambda: MagicMock())
    monkeypatch.setattr(routes, "upload_file", AsyncMock(side_effect=OSError("MinIO unavailable")))

    with pytest.raises(HTTPException) as unavailable:
        await routes.upload_quote_file(
            "task_1",
            UploadFile(filename="quote.pdf", file=io.BytesIO(b"%PDF-demo"), headers={"content-type": "application/pdf"}),
            _user("operator"),
        )

    assert unavailable.value.status_code == 503
    database.create_artifact.assert_not_awaited()
