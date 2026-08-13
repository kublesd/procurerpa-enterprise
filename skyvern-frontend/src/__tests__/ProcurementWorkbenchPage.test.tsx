import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ProcurementWorkbenchPage } from "@/routes/enterprise/procurement/ProcurementWorkbenchPage";
import { authFetch } from "@/util/authFetch";

vi.mock("@/util/authFetch", () => ({ authFetch: vi.fn() }));

const mockedAuthFetch = vi.mocked(authFetch);

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const quote = (suffix: string) => ({
  quote_id: `quote-${suffix}`,
  task_id: `task-${suffix}`,
  organization_id: "org-demo",
  department_id: "dept-it",
  category_id: "category-it",
  supplier_id: `supplier-${suffix}`,
  material_name: "SSD",
  quantity: "10",
  unit: "unit",
  currency: "CNY",
  unit_price_cny: suffix === "alpha" ? "10" : "11",
  freight_cny: "1",
  moq: "1",
  delivery_days: suffix === "alpha" ? 5 : 7,
  artifact_id: `artifact-${suffix}`,
  created_by: "it-buyer",
});

describe("ProcurementWorkbenchPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("collects both supplier quotes and displays the backend comparison", async () => {
    vi.stubGlobal("crypto", { randomUUID: () => "idempotency-key" });
    mockedAuthFetch.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return jsonResponse({ org_id: "org-demo" });
      if (url.endsWith("/context-options")) {
        return jsonResponse({
          departments: [
            { department_id: "dept-it", name: "IT Procurement", code: "IT" },
          ],
          categories: [
            { category_id: "category-it", name: "IT Hardware", code: "IT-HW" },
          ],
        });
      }
      if (url.endsWith("/quote-task")) {
        const payload = JSON.parse(String(init?.body ?? "{}")) as {
          url?: string;
        };
        const suffix = payload.url?.includes("vendor-a") ? "alpha" : "beta";
        return jsonResponse({
          task_id: `task-${suffix}`,
          task_status: suffix === "beta" ? "running" : "completed",
          outcome: suffix === "beta" ? "running" : "completed",
          idempotent: false,
          approval_id: null,
          quote_id: `quote-${suffix}`,
          artifact_id: `artifact-${suffix}`,
        });
      }
      if (url.endsWith("/tasks/task-beta")) {
        return jsonResponse({ task_id: "task-beta", status: "completed" });
      }
      if (url.includes("/quotes/compare?")) {
        return jsonResponse({
          task_ids: ["task-alpha", "task-beta"],
          quotes: [
            {
              task_id: "task-alpha",
              artifact_id: "artifact-alpha",
              quote_id: "quote-alpha",
              supplier_id: "supplier-alpha",
              total_cny: "101",
              landed_unit_price_cny: "10.1",
              delivery_days: 5,
              eligible: true,
              rank: 1,
              reason: "lowest landed unit price",
            },
            {
              task_id: "task-beta",
              artifact_id: "artifact-beta",
              quote_id: "quote-beta",
              supplier_id: "supplier-beta",
              total_cny: "112",
              landed_unit_price_cny: "11.2",
              delivery_days: 7,
              eligible: true,
              rank: 2,
              reason: "higher landed unit price",
            },
          ],
          recommended_quote_id: "quote-alpha",
          recommendation_reason: "deterministic landed-price rule",
        });
      }
      if (url.includes("task-alpha"))
        return jsonResponse({ quotes: [quote("alpha")], total: 1 });
      if (url.includes("task-beta"))
        return jsonResponse({ quotes: [quote("beta")], total: 1 });
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<ProcurementWorkbenchPage />);
    const button = await waitFor(() => {
      const element = screen.getByRole("button", {
        name: "开始采集报价",
      }) as HTMLButtonElement;
      if (element.disabled) throw new Error("workbench is still loading");
      return element;
    });

    fireEvent.click(button);

    await waitFor(() => expect(screen.getByText(/task-alpha/)).not.toBeNull());
    expect(screen.getByText(/task-beta/)).not.toBeNull();
    expect(screen.getAllByText(/artifact-alpha/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/artifact-beta/).length).toBeGreaterThan(0);
    expect(screen.getByText(/deterministic landed-price rule/)).not.toBeNull();
  });

  it("shows the context error without demo quote data", async () => {
    mockedAuthFetch.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return jsonResponse({ org_id: "org-demo" });
      if (url.endsWith("/context-options"))
        return jsonResponse({ detail: "context unavailable" }, 500);
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<ProcurementWorkbenchPage />);

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "context unavailable",
      ),
    );
    expect(screen.getByText(/尚未采集到已校验报价/)).not.toBeNull();
    expect(screen.queryByText("deterministic landed-price rule")).toBeNull();
  });
});
