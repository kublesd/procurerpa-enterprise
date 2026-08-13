"""Run the procurement happy-path smoke test against the running Skyvern API."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from enterprise.procurement.seed import seed_procurement_data
from skyvern.config import settings
from skyvern.forge import app
from skyvern.forge.forge_app_initializer import start_forge_app
from skyvern.forge.sdk.api.llm.config_registry import LLMConfigRegistry

DEFAULT_QUOTE_URLS = (
    "http://host.docker.internal:18080/procurement/vendor-a.html",
    "http://host.docker.internal:18080/procurement/vendor-b.html",
)
DEFAULT_SMOKE_URL = "https://example.com/"
CONTROLLED_PDF = b"%PDF-1.4\n% ProcureRPA controlled SIT\n%%EOF\n"


class ApiError(RuntimeError):
    def __init__(self, status: int, body: Any) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


def api_request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    timeout: int = 30,
) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            response_body: Any = json.loads(raw)
        except json.JSONDecodeError:
            response_body = raw
        raise ApiError(exc.code, response_body) from None


async def seed_demo() -> dict[str, int]:
    async with app.DATABASE.Session() as session:
        created = await seed_procurement_data(session)
        await session.commit()
    return created


def check_llm_key() -> None:
    key = settings.LLM_KEY.upper()
    if key.startswith("GEMINI_") and settings.LLM_KEY not in LLMConfigRegistry.get_model_names():
        raise RuntimeError(f"LLM {settings.LLM_KEY} is not registered; choose a configured Gemini model")
    if key.startswith("GEMINI_"):
        env_name, value = "GEMINI_API_KEY", settings.GEMINI_API_KEY
    elif key.startswith("OPENAI_"):
        env_name, value = "OPENAI_API_KEY", settings.OPENAI_API_KEY
    elif key.startswith("ANTHROPIC_"):
        env_name, value = "ANTHROPIC_API_KEY", settings.ANTHROPIC_API_KEY
    else:
        env_name, value = "LLM_API_KEY", settings.LLM_API_KEY
    if not value:
        raise RuntimeError(f"LLM {settings.LLM_KEY} is missing: {env_name}")
    print(f"LLM: {settings.LLM_KEY} ({env_name}=set)")


def login(args: argparse.Namespace, username: str, password: str) -> dict[str, Any]:
    return api_request(
        args.base_url,
        "POST",
        "/enterprise/auth/login",
        body={
            "username": username,
            "password": password,
            "organization_id": args.organization_id,
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--scenario", choices=("quotes", "controls", "all"), default="quotes")
    parser.add_argument("--username", default="it_buyer")
    parser.add_argument("--password", default="demo123")
    parser.add_argument("--approver-username", default="procurement_approver")
    parser.add_argument("--approver-password", default="demo123")
    parser.add_argument("--audit-username", default="procurement_admin")
    parser.add_argument("--audit-password", default="demo123")
    parser.add_argument("--organization-id", default="org_procurement_demo")
    parser.add_argument("--department-id", default="dept_it_procurement")
    parser.add_argument("--category-id", default="pc_it")
    parser.add_argument("--smoke-url", default=DEFAULT_SMOKE_URL)
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        default=None,
        help="Supplier page URL; repeat twice, or use --quote-urls.",
    )
    parser.add_argument(
        "--quote-urls",
        default=os.getenv("PROCUREMENT_QUOTE_URLS", ",".join(DEFAULT_QUOTE_URLS)),
        help="Comma-separated URLs for the two controlled supplier pages.",
    )
    parser.add_argument("--timeout", type=int, default=900, help="Maximum seconds for the browser task")
    return parser.parse_args()


def _quote_urls(args: argparse.Namespace) -> list[str]:
    quote_urls = args.urls or [url.strip() for url in args.quote_urls.split(",") if url.strip()]
    if len(quote_urls) != 2:
        raise RuntimeError("Day 11 smoke requires exactly two supplier URLs")
    return quote_urls


def run_quotes(args: argparse.Namespace, buyer_token: str, audit_token: str) -> list[str]:
    quote_urls = _quote_urls(args)
    print(f"[quotes] Checking supplier pages: {', '.join(quote_urls)}")
    for quote_url in quote_urls:
        with urllib.request.urlopen(quote_url, timeout=20) as quote_page:
            if quote_page.status >= 400:
                raise RuntimeError("Supplier page health check failed")

    print("[quotes] Running two Skyvern quote tasks")
    task_ids: list[str] = []
    quote_ids: list[str] = []
    try:
        for index, quote_url in enumerate(quote_urls, start=1):
            result = api_request(
                args.base_url,
                "POST",
                "/enterprise/procurement/quote-task",
                token=buyer_token,
                idempotency_key=str(uuid4()),
                body={
                    "organization_id": args.organization_id,
                    "department_id": args.department_id,
                    "category_id": args.category_id,
                    "url": quote_url,
                    "risk": {
                        "total_amount_cny": "1000",
                        "supplier_id": "supplier-demo",
                        "supplier_qualified": True,
                        "selected_quote_cny": "100",
                        "average_quote_cny": "100",
                        "operation_type": "standard",
                        "redacted_description": "Allowlisted procurement quote task",
                    },
                },
                timeout=args.timeout,
            )
            if result.get("outcome") != "completed" or not result.get("quote_id"):
                raise RuntimeError(f"Supplier {index} quote task did not complete")
            task_ids.append(result["task_id"])
            quote_ids.append(result["quote_id"])
            print(
                f"[quotes] supplier={index} task_id={result['task_id']} "
                f"quote_id={result['quote_id']} artifact_id={result.get('artifact_id')} status=completed"
            )
    except ApiError as exc:
        print(f"Quote task failed: {exc}", file=sys.stderr)
        raise

    for task_id in task_ids:
        task = api_request(args.base_url, "GET", f"/enterprise/procurement/tasks/{task_id}", token=buyer_token)
        if task.get("status") != "completed":
            raise RuntimeError(f"Quote task {task_id} is not completed")
    comparison = api_request(
        args.base_url,
        "GET",
        f"/enterprise/procurement/quotes/compare?{urlencode([('task_ids', task_id) for task_id in task_ids])}",
        token=buyer_token,
    )
    comparison_quotes = comparison.get("quotes", [])
    if (
        len(comparison_quotes) != 2
        or comparison.get("recommended_quote_id") not in quote_ids
        or {item["task_id"] for item in comparison_quotes} != set(task_ids)
        or not all(item.get("artifact_id") for item in comparison_quotes)
    ):
        raise RuntimeError("Comparison did not preserve both task and artifact references")
    print(f"[quotes] comparison tasks={len(task_ids)} recommended_quote_id={comparison['recommended_quote_id']} PASS")

    for task_id in task_ids:
        audit = api_request(
            args.base_url,
            "GET",
            f"/enterprise/audit/logs?task_id={task_id}",
            token=audit_token,
        )
        if not audit.get("items"):
            raise RuntimeError(f"No audit records found for quote task {task_id}")
    print(f"[quotes] audit_tasks={len(task_ids)} PASS")
    return task_ids


def _high_risk_request(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "organization_id": args.organization_id,
        "department_id": args.department_id,
        "category_id": args.category_id,
        "url": args.smoke_url,
        "risk": {
            "total_amount_cny": "100000",
            "supplier_id": "controlled-demo-supplier",
            "supplier_qualified": True,
            "selected_quote_cny": "100",
            "average_quote_cny": "100",
            "operation_type": "standard",
            "redacted_description": "Controlled high-value procurement smoke",
        },
    }


def _wait_for_task(args: argparse.Namespace, token: str, task_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + args.timeout
    while True:
        task = api_request(args.base_url, "GET", f"/enterprise/procurement/tasks/{task_id}", token=token)
        task_status = task.get("status")
        if task_status == "completed":
            return task
        if task_status in {"failed", "terminated", "timed_out", "canceled"}:
            raise RuntimeError(f"Task {task_id} ended with status={task_status}")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Task {task_id} did not complete within timeout")
        time.sleep(2)


def upload_quote_pdf(base_url: str, token: str, task_id: str) -> dict[str, Any]:
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/enterprise/audit/tasks/{task_id}/quote-files",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("controlled-quote.pdf", CONTROLLED_PDF, "application/pdf")},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError("MinIO quote file upload failed") from exc
    if response.status_code >= 400:
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text[:200]
        raise ApiError(response.status_code, body)
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("Quote file upload returned invalid JSON") from exc


def verify_pdf_readback(url: str) -> None:
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        raise RuntimeError("MinIO quote file readback failed") from exc
    if response.status_code >= 400 or not response.content.startswith(b"%PDF-"):
        raise RuntimeError("MinIO quote file readback was not a PDF")


def run_controls(args: argparse.Namespace, buyer_token: str, approver_token: str, audit_token: str) -> None:
    request = _high_risk_request(args)
    print("[controls] Creating high-risk approval")
    pending = api_request(
        args.base_url,
        "POST",
        "/enterprise/procurement/smoke-task",
        token=buyer_token,
        idempotency_key=str(uuid4()),
        body=request,
    )
    approval_id = pending.get("approval_id")
    task_id = pending.get("task_id")
    if (
        pending.get("outcome") != "pending_approval"
        or pending.get("task_status") != "created"
        or not approval_id
        or not task_id
    ):
        raise RuntimeError("High-risk task did not create a pending approval")

    approver_me = api_request(args.base_url, "GET", "/enterprise/auth/me", token=approver_token)
    approvals = api_request(args.base_url, "GET", "/enterprise/approvals/pending", token=approver_token)
    approval = next((item for item in approvals if item.get("approval_id") == approval_id), None)
    if approval is None or approval.get("requester_user_id") == approver_me.get("user_id"):
        raise RuntimeError("Pending approval is missing or permits self-approval")
    print(f"[controls] pending task_id={task_id} approval_id={approval_id} status=pending")

    decision = api_request(
        args.base_url,
        "POST",
        f"/enterprise/approvals/{approval_id}/approve",
        token=approver_token,
        body={"note": "Controlled SIT approval"},
    )
    if decision.get("status") != "approved":
        raise RuntimeError("High-risk approval did not become approved")
    continued = api_request(
        args.base_url,
        "POST",
        f"/enterprise/approvals/{approval_id}/continue",
        token=buyer_token,
    )
    if continued.get("task_id") != task_id or continued.get("task_status") != "running":
        raise RuntimeError("Approved task did not continue as the same running Task")
    _wait_for_task(args, buyer_token, task_id)
    print(f"[controls] approved task_id={task_id} approval_id={approval_id} status=completed PASS")

    rejected = api_request(
        args.base_url,
        "POST",
        "/enterprise/procurement/smoke-task",
        token=buyer_token,
        idempotency_key=str(uuid4()),
        body=request,
    )
    rejected_approval_id = rejected.get("approval_id")
    rejected_task_id = rejected.get("task_id")
    if not rejected_approval_id or not rejected_task_id or rejected.get("outcome") != "pending_approval":
        raise RuntimeError("Rejection scenario did not create a pending approval")
    rejection = api_request(
        args.base_url,
        "POST",
        f"/enterprise/approvals/{rejected_approval_id}/reject",
        token=approver_token,
        body={"note": "Controlled SIT rejection"},
    )
    if rejection.get("status") != "rejected":
        raise RuntimeError("Approval rejection did not become rejected")
    rejected_task = api_request(
        args.base_url,
        "GET",
        f"/enterprise/procurement/tasks/{rejected_task_id}",
        token=buyer_token,
    )
    if rejected_task.get("status") != "canceled":
        raise RuntimeError("Rejected approval did not cancel the original Task")
    try:
        api_request(
            args.base_url,
            "POST",
            f"/enterprise/approvals/{rejected_approval_id}/continue",
            token=buyer_token,
        )
    except ApiError as exc:
        if exc.status != 409:
            raise RuntimeError(f"Rejected Task continue returned HTTP {exc.status}") from None
    else:
        raise RuntimeError("Rejected Task was allowed to continue")
    print(f"[controls] rejected task_id={rejected_task_id} approval_id={rejected_approval_id} status=canceled PASS")

    uploaded = upload_quote_pdf(args.base_url, buyer_token, task_id)
    artifact_id = uploaded.get("artifact_id")
    object_uri = uploaded.get("object_uri")
    presigned_url = uploaded.get("presigned_url")
    if not artifact_id or not object_uri or not object_uri.startswith("minio://") or not presigned_url:
        raise RuntimeError("Quote PDF upload did not return MinIO and Artifact evidence")
    verify_pdf_readback(presigned_url)
    audit = api_request(
        args.base_url,
        "GET",
        f"/enterprise/audit/logs?task_id={task_id}",
        token=audit_token,
    )
    if not any(item.get("action_type") == "quote_file_uploaded" for item in audit.get("items", [])):
        raise RuntimeError("Quote PDF upload audit event was not persisted")
    print(f"[controls] pdf task_id={task_id} artifact_id={artifact_id} audit=quote_file_uploaded PASS")


def main() -> int:
    args = parse_args()
    if args.timeout <= 0:
        raise RuntimeError("--timeout must be positive")
    start_forge_app()
    print(f"[setup] seed={asyncio.run(seed_demo())}")

    health = api_request(args.base_url, "GET", "/enterprise/procurement/health?ready=true")
    if not health.get("ready"):
        raise RuntimeError("Service is not ready")
    check_llm_key()

    buyer_login = login(args, args.username, args.password)
    audit_login = login(args, args.audit_username, args.audit_password)
    approver_login = None
    if args.scenario in {"controls", "all"}:
        approver_login = login(args, args.approver_username, args.approver_password)

    if args.scenario in {"quotes", "all"}:
        run_quotes(args, buyer_login["access_token"], audit_login["access_token"])
    if args.scenario in {"controls", "all"}:
        assert approver_login is not None
        run_controls(
            args,
            buyer_login["access_token"],
            approver_login["access_token"],
            audit_login["access_token"],
        )

    print(f"PASS: scenario={args.scenario}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ApiError, KeyError, RuntimeError, urllib.error.URLError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
