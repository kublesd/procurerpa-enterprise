import { useEffect, useRef, useState } from "react";
import { GlassCard } from "@/components/enterprise/GlassCard";
import { StatusBadge } from "@/components/enterprise/StatusBadge";
import { useI18n } from "@/i18n/useI18n";
import { authFetch } from "@/util/authFetch";

type ContextResponse = {
  departments: Array<{ department_id: string; name: string; code: string }>;
  categories: Array<{ category_id: string; name: string; code: string }>;
};

type UserResponse = { org_id: string };

type QuoteTaskResult = {
  task_id: string;
  task_status: string;
  outcome: "completed" | "failed" | "pending_approval" | "rejected" | "running";
  idempotent: boolean;
  approval_id: string | null;
  quote_id: string | null;
  artifact_id: string | null;
};

type TaskResponse = { task_id: string; status: string };

type Quote = {
  quote_id: string;
  task_id: string;
  supplier_id: string;
  material_name: string;
  quantity: string;
  unit: "unit";
  currency: "CNY";
  unit_price_cny: string;
  freight_cny: string;
  moq: string;
  delivery_days: number;
  artifact_id: string;
};

type QuoteListResponse = { quotes: Quote[]; total: number };

type Comparison = {
  task_ids: string[];
  quotes: Array<{
    task_id: string;
    artifact_id: string;
    quote_id: string;
    supplier_id: string;
    total_cny: string;
    landed_unit_price_cny: string;
    delivery_days: number;
    eligible: boolean;
    rank: number | null;
    reason: string;
  }>;
  recommended_quote_id: string | null;
  recommendation_reason: string;
};

const SUPPLIER_PAGES = [
  {
    key: "alpha",
    labelKey: "procurement.supplierAlpha",
    url: "http://host.docker.internal:18080/procurement/vendor-a.html",
  },
  {
    key: "beta",
    labelKey: "procurement.supplierBeta",
    url: "http://host.docker.internal:18080/procurement/vendor-b.html",
  },
] as const;

type SupplierKey = (typeof SUPPLIER_PAGES)[number]["key"];
type SupplierPage = (typeof SUPPLIER_PAGES)[number];

type RunState = {
  state: "idle" | "running" | "completed" | "error";
  taskStatus: string;
  taskId: string | null;
  quoteId: string | null;
  artifactId: string | null;
  message: string | null;
};

const TERMINAL_TASK_STATUSES = new Set([
  "failed",
  "timed_out",
  "terminated",
  "canceled",
  "timeout",
]);

function initialRuns(): Record<SupplierKey, RunState> {
  return {
    alpha: {
      state: "idle",
      taskStatus: "",
      taskId: null,
      quoteId: null,
      artifactId: null,
      message: null,
    },
    beta: {
      state: "idle",
      taskStatus: "",
      taskId: null,
      quoteId: null,
      artifactId: null,
      message: null,
    },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

async function responseError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (isRecord(body)) {
      const detail = body.detail;
      if (typeof detail === "string" && detail.trim()) return detail;
      if (isRecord(detail)) {
        for (const key of ["reason", "message", "code"]) {
          if (typeof detail[key] === "string" && detail[key])
            return detail[key] as string;
        }
      }
    }
  } catch {
    // Use the status below when the response is not JSON.
  }
  return `HTTP ${response.status}`;
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authFetch(path, init);
  if (!response.ok) throw new Error(await responseError(response));
  return (await response.json()) as T;
}

function errorText(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : "Request failed";
}

function createIdempotencyKey(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

export function ProcurementWorkbenchPage() {
  const { t } = useI18n();
  const isMounted = useRef(false);
  const [organizationId, setOrganizationId] = useState("");
  const [contexts, setContexts] = useState<ContextResponse>({
    departments: [],
    categories: [],
  });
  const [departmentId, setDepartmentId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [runs, setRuns] = useState<Record<SupplierKey, RunState>>(initialRuns);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    isMounted.current = true;

    async function loadContext() {
      try {
        const [user, context] = await Promise.all([
          getJson<UserResponse>("/api/v1/enterprise/auth/me"),
          getJson<ContextResponse>(
            "/api/v1/enterprise/procurement/context-options",
          ),
        ]);
        if (!isMounted.current) return;
        const departments = context.departments ?? [];
        const categories = context.categories ?? [];
        setOrganizationId(user.org_id);
        setContexts({ departments, categories });
        setDepartmentId(departments[0]?.department_id ?? "");
        setCategoryId(categories[0]?.category_id ?? "");
      } catch (loadError) {
        if (isMounted.current) setError(errorText(loadError));
      } finally {
        if (isMounted.current) setLoading(false);
      }
    }

    void loadContext();
    return () => {
      isMounted.current = false;
    };
  }, []);

  function updateRun(key: SupplierKey, patch: Partial<RunState>) {
    if (!isMounted.current) return;
    setRuns((current) => ({
      ...current,
      [key]: { ...current[key], ...patch },
    }));
  }

  async function startQuote(page: SupplierPage): Promise<QuoteTaskResult> {
    if (!organizationId || !departmentId || !categoryId) {
      throw new Error(t("procurement.organizationUnavailable"));
    }
    const response = await authFetch(
      "/api/v1/enterprise/procurement/quote-task",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": createIdempotencyKey(),
        },
        body: JSON.stringify({
          organization_id: organizationId,
          department_id: departmentId,
          category_id: categoryId,
          url: page.url,
          risk: {
            total_amount_cny: "1000",
            supplier_id: "controlled-demo-supplier",
            supplier_qualified: true,
            selected_quote_cny: "100",
            average_quote_cny: "100",
            operation_type: "standard",
            redacted_description: "Controlled supplier quote collection",
          },
        }),
      },
    );
    if (!response.ok) throw new Error(await responseError(response));
    return (await response.json()) as QuoteTaskResult;
  }

  async function waitForTask(taskId: string): Promise<TaskResponse> {
    for (let attempt = 0; attempt < 150; attempt += 1) {
      const task = await getJson<TaskResponse>(
        `/api/v1/enterprise/procurement/tasks/${encodeURIComponent(taskId)}`,
      );
      if (!isMounted.current) throw new Error("Page was closed");
      if (task.status === "completed") return task;
      if (TERMINAL_TASK_STATUSES.has(task.status)) {
        throw new Error(t("procurement.taskEnded", { status: task.status }));
      }
      if (attempt < 149) {
        await new Promise<void>((resolve) => window.setTimeout(resolve, 2000));
      }
    }
    throw new Error(t("procurement.taskStillRunning"));
  }

  async function loadQuote(taskId: string): Promise<Quote> {
    const data = await getJson<QuoteListResponse>(
      `/api/v1/enterprise/procurement/quotes?task_id=${encodeURIComponent(taskId)}`,
    );
    const quote = data.quotes[0];
    if (data.total !== 1 || data.quotes.length !== 1 || !quote) {
      throw new Error(t("procurement.quoteCountError"));
    }
    return quote;
  }

  async function loadComparison(taskIds: string[]): Promise<Comparison> {
    const query = new URLSearchParams();
    taskIds.forEach((taskId) => query.append("task_ids", taskId));
    return getJson<Comparison>(
      `/api/v1/enterprise/procurement/quotes/compare?${query.toString()}`,
    );
  }

  async function runCollection() {
    if (loading || !organizationId || !departmentId || !categoryId) return;
    setLoading(true);
    setError(null);
    setQuotes([]);
    setComparison(null);
    setRuns(initialRuns());

    const taskIds: string[] = [];
    const collectedQuotes: Quote[] = [];
    try {
      for (const page of SUPPLIER_PAGES) {
        if (!isMounted.current) return;
        try {
          updateRun(page.key, { state: "running", message: null });
          const result = await startQuote(page);
          taskIds.push(result.task_id);
          let taskStatus = result.task_status;
          updateRun(page.key, {
            taskId: result.task_id,
            taskStatus,
            quoteId: result.quote_id,
            artifactId: result.artifact_id,
          });
          let completed = result.outcome === "completed";
          if (result.outcome === "running") {
            taskStatus = (await waitForTask(result.task_id)).status;
            completed = taskStatus === "completed";
            updateRun(page.key, { taskStatus });
          }
          if (!completed) {
            throw new Error(
              t("procurement.taskNotCompleted", { status: result.outcome }),
            );
          }
          const quote = await loadQuote(result.task_id);
          collectedQuotes.push(quote);
          setQuotes([...collectedQuotes]);
          updateRun(page.key, {
            state: "completed",
            taskStatus,
            quoteId: quote.quote_id,
            artifactId: quote.artifact_id,
          });
        } catch (runError) {
          updateRun(page.key, { state: "error", message: errorText(runError) });
          throw runError;
        }
      }
      const result = await loadComparison(taskIds);
      if (isMounted.current) setComparison(result);
    } catch (collectionError) {
      if (isMounted.current) setError(errorText(collectionError));
    } finally {
      if (isMounted.current) setLoading(false);
    }
  }

  const noContext =
    !loading && (!contexts.departments.length || !contexts.categories.length);

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1
          className="text-xl font-bold"
          style={{ color: "var(--procurerpa-blue)" }}
        >
          {t("procurement.title")}
        </h1>
        <p
          className="mt-1 text-sm"
          style={{ color: "var(--procurerpa-text-secondary)" }}
        >
          {t("procurement.subtitle")}
        </p>
      </div>

      {error && (
        <div
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
          role="alert"
        >
          {error}
        </div>
      )}

      <GlassCard hoverable={false}>
        <h2
          className="mb-4 text-base font-semibold"
          style={{ color: "var(--procurerpa-text-primary)" }}
        >
          {t("procurement.collectionSettings")}
        </h2>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void runCollection();
          }}
        >
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label
                className="mb-1 block text-sm font-medium"
                htmlFor="procurement-department"
              >
                {t("procurement.department")}
              </label>
              <select
                className="glass-input w-full"
                disabled={loading || !contexts.departments.length}
                id="procurement-department"
                value={departmentId}
                onChange={(event) => setDepartmentId(event.target.value)}
              >
                {contexts.departments.map((department) => (
                  <option
                    key={department.department_id}
                    value={department.department_id}
                  >
                    {department.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                className="mb-1 block text-sm font-medium"
                htmlFor="procurement-category"
              >
                {t("procurement.category")}
              </label>
              <select
                className="glass-input w-full"
                disabled={loading || !contexts.categories.length}
                id="procurement-category"
                value={categoryId}
                onChange={(event) => setCategoryId(event.target.value)}
              >
                {contexts.categories.map((category) => (
                  <option
                    key={category.category_id}
                    value={category.category_id}
                  >
                    {category.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <span className="mb-1 block text-sm font-medium">
              {t("procurement.suppliers")}
            </span>
            <div className="grid gap-3 md:grid-cols-2">
              {SUPPLIER_PAGES.map((page) => (
                <div className="rounded-lg border p-3" key={page.key}>
                  <div
                    className="text-sm font-medium"
                    style={{ color: "var(--procurerpa-text-primary)" }}
                  >
                    {t(page.labelKey)}
                  </div>
                  <div
                    className="mt-1 break-all text-xs"
                    style={{ color: "var(--procurerpa-text-muted)" }}
                  >
                    {page.url}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {noContext && (
            <p
              className="text-sm"
              style={{ color: "var(--procurerpa-text-secondary)" }}
            >
              {t("procurement.noContext")}
            </p>
          )}
          <button
            className="glass-btn-primary"
            disabled={
              loading ||
              noContext ||
              !organizationId ||
              !departmentId ||
              !categoryId
            }
            type="submit"
          >
            {loading
              ? t("procurement.collecting")
              : t("procurement.startCollection")}
          </button>
        </form>
      </GlassCard>

      <GlassCard hoverable={false}>
        <h2
          className="mb-4 text-base font-semibold"
          style={{ color: "var(--procurerpa-text-primary)" }}
        >
          {t("procurement.taskStatus")}
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          {SUPPLIER_PAGES.map((page) => {
            const run = runs[page.key];
            return (
              <div className="rounded-lg border p-4" key={page.key}>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <span
                    className="font-medium"
                    style={{ color: "var(--procurerpa-text-primary)" }}
                  >
                    {t(page.labelKey)}
                  </span>
                  {run.taskStatus ? (
                    <StatusBadge status={run.taskStatus} />
                  ) : (
                    <span
                      className="text-xs"
                      style={{ color: "var(--procurerpa-text-muted)" }}
                    >
                      {t("procurement.notStarted")}
                    </span>
                  )}
                </div>
                <div
                  className="space-y-1 text-xs"
                  style={{ color: "var(--procurerpa-text-secondary)" }}
                >
                  <div>
                    {t("procurement.taskId")}: {run.taskId ?? "—"}
                  </div>
                  <div>
                    {t("procurement.quoteId")}: {run.quoteId ?? "—"}
                  </div>
                  <div>
                    {t("procurement.artifactId")}: {run.artifactId ?? "—"}
                  </div>
                </div>
                {run.message && (
                  <p className="mt-2 text-sm text-red-700">{run.message}</p>
                )}
              </div>
            );
          })}
        </div>
      </GlassCard>

      <GlassCard hoverable={false}>
        <h2
          className="mb-4 text-base font-semibold"
          style={{ color: "var(--procurerpa-text-primary)" }}
        >
          {t("procurement.quotes")}
        </h2>
        {quotes.length === 0 ? (
          <p
            className="text-sm"
            style={{ color: "var(--procurerpa-text-secondary)" }}
          >
            {t("procurement.noQuotes")}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr
                  className="border-b text-xs"
                  style={{ color: "var(--procurerpa-text-muted)" }}
                >
                  <th className="px-2 py-2">{t("procurement.supplier")}</th>
                  <th className="px-2 py-2">{t("procurement.material")}</th>
                  <th className="px-2 py-2">{t("procurement.quantity")}</th>
                  <th className="px-2 py-2">{t("procurement.unitPrice")}</th>
                  <th className="px-2 py-2">{t("procurement.freight")}</th>
                  <th className="px-2 py-2">{t("procurement.moq")}</th>
                  <th className="px-2 py-2">{t("procurement.deliveryDays")}</th>
                </tr>
              </thead>
              <tbody>
                {quotes.map((quote) => (
                  <tr className="border-b last:border-0" key={quote.quote_id}>
                    <td className="px-2 py-2">{quote.supplier_id}</td>
                    <td className="px-2 py-2">{quote.material_name}</td>
                    <td className="px-2 py-2">
                      {quote.quantity} {quote.unit}
                    </td>
                    <td className="px-2 py-2">
                      {quote.unit_price_cny} {quote.currency}
                    </td>
                    <td className="px-2 py-2">
                      {quote.freight_cny} {quote.currency}
                    </td>
                    <td className="px-2 py-2">{quote.moq}</td>
                    <td className="px-2 py-2">{quote.delivery_days}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      <GlassCard hoverable={false}>
        <h2
          className="mb-4 text-base font-semibold"
          style={{ color: "var(--procurerpa-text-primary)" }}
        >
          {t("procurement.comparison")}
        </h2>
        {comparison ? (
          <>
            <p
              className="mb-4 text-sm"
              style={{ color: "var(--procurerpa-text-secondary)" }}
            >
              {t("procurement.recommendation")}:{" "}
              {comparison.recommendation_reason}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr
                    className="border-b text-xs"
                    style={{ color: "var(--procurerpa-text-muted)" }}
                  >
                    <th className="px-2 py-2">{t("procurement.supplier")}</th>
                    <th className="px-2 py-2">{t("procurement.total")}</th>
                    <th className="px-2 py-2">
                      {t("procurement.landedUnitPrice")}
                    </th>
                    <th className="px-2 py-2">{t("procurement.eligible")}</th>
                    <th className="px-2 py-2">{t("procurement.rank")}</th>
                    <th className="px-2 py-2">{t("procurement.reason")}</th>
                    <th className="px-2 py-2">{t("procurement.evidence")}</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.quotes.map((item) => (
                    <tr className="border-b last:border-0" key={item.quote_id}>
                      <td className="px-2 py-2">
                        {item.supplier_id}
                        {item.quote_id === comparison.recommended_quote_id && (
                          <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">
                            {t("procurement.recommended")}
                          </span>
                        )}
                      </td>
                      <td className="px-2 py-2">{item.total_cny} CNY</td>
                      <td className="px-2 py-2">
                        {item.landed_unit_price_cny} CNY
                      </td>
                      <td className="px-2 py-2">
                        {item.eligible ? t("common.yes") : t("common.no")}
                      </td>
                      <td className="px-2 py-2">{item.rank ?? "—"}</td>
                      <td className="px-2 py-2">{item.reason}</td>
                      <td className="px-2 py-2">
                        <div>
                          {t("procurement.artifactId")}: {item.artifact_id}
                        </div>
                        <a
                          className="text-blue-700 underline"
                          href={`/tasks/${encodeURIComponent(item.task_id)}/diagnostics`}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {t("procurement.openDiagnostics")}
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p
            className="text-sm"
            style={{ color: "var(--procurerpa-text-secondary)" }}
          >
            {t("procurement.noComparison")}
          </p>
        )}
      </GlassCard>
    </div>
  );
}
