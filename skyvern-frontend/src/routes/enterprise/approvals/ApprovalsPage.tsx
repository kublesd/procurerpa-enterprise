import { useEffect, useState } from "react";
import { GlassCard } from "@/components/enterprise/GlassCard";
import { RiskBadge } from "@/components/enterprise/RiskBadge";
import { Icon } from "@/components/Icon";
import { useI18n } from "@/i18n/useI18n";
import { authFetch } from "@/util/authFetch";

type ApprovalRequest = {
  approval_id: string;
  task_id: string;
  risk_level: string;
  risk_reason: string;
  operation_description: string | null;
  department_id: string;
  requested_at: string;
  screenshot_path?: string | null;
  status: string;
};

async function responseError(response: Response): Promise<Error> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return new Error(body.detail);
  } catch {
    // Use the HTTP status below when the response is not JSON.
  }
  return new Error(`HTTP ${response.status}`);
}

function ApprovalCard({
  item,
  onApprove,
  onReject,
}: {
  item: ApprovalRequest;
  onApprove: (id: string, note: string) => void;
  onReject: (id: string, note: string) => void;
}) {
  const { t } = useI18n();
  const [remark, setRemark] = useState("");

  return (
    <GlassCard hoverable={false} padding="md" className="mb-4">
      <div className="flex gap-6">
        <div className="hidden w-48 shrink-0 sm:block">
          {item.screenshot_path ? (
            <img
              src={item.screenshot_path}
              alt="Task screenshot"
              className="h-32 w-full rounded-lg border border-gray-200 object-cover"
            />
          ) : (
            <div className="flex h-32 w-full items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50">
              <span className="text-xs text-gray-400">
                {t("approvals.noScreenshot")}
              </span>
            </div>
          )}
        </div>

        <div className="flex-1">
          <div className="mb-2 flex items-center gap-3">
            <RiskBadge level={item.risk_level} />
            <span
              className="text-xs"
              style={{ color: "var(--procurerpa-text-muted)" }}
            >
              {item.department_id}
            </span>
          </div>
          <h3
            className="text-sm font-semibold"
            style={{ color: "var(--procurerpa-text-primary)" }}
          >
            {item.operation_description ?? item.task_id}
          </h3>
          <p
            className="mt-1 text-sm"
            style={{ color: "var(--procurerpa-text-secondary)" }}
          >
            {item.risk_reason}
          </p>
          <div
            className="mt-2 flex items-center gap-4 text-xs"
            style={{ color: "var(--procurerpa-text-muted)" }}
          >
            <span>
              {t("approvals.task")}: {item.task_id}
            </span>
            <span>
              {t("approvals.requested")}:{" "}
              {new Date(item.requested_at).toLocaleString()}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 flex-col gap-2" style={{ width: 180 }}>
          <input
            className="glass-input text-xs"
            placeholder={t("approvals.remarkPlaceholder")}
            value={remark}
            onChange={(event) => setRemark(event.target.value)}
          />
          <button
            className="glass-btn-primary flex items-center justify-center gap-1 text-sm"
            onClick={() => onApprove(item.approval_id, remark)}
          >
            <Icon name="check-circle" size={16} color="white" />
            {t("approvals.approve")}
          </button>
          <button
            className="flex items-center justify-center gap-1 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
            onClick={() => onReject(item.approval_id, remark)}
          >
            <Icon name="x-circle" size={16} color="#DC2626" />
            {t("approvals.reject")}
          </button>
        </div>
      </div>
    </GlassCard>
  );
}

export function ApprovalsPage() {
  const { t } = useI18n();
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    authFetch("/api/v1/enterprise/approvals/pending")
      .then(async (response) => {
        if (!response.ok) throw await responseError(response);
        return response.json() as Promise<ApprovalRequest[]>;
      })
      .then((data) => {
        if (active) setApprovals(data);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setApprovals([]);
        setError(
          reason instanceof Error ? reason.message : t("approvals.loadError"),
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [t]);

  async function handleDecision(
    id: string,
    decision: "approve" | "reject",
    note: string,
  ) {
    setActionError(null);
    try {
      const response = await authFetch(
        `/api/v1/enterprise/approvals/${id}/${decision}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note }),
        },
      );
      if (!response.ok) throw await responseError(response);
      setApprovals((previous) =>
        previous.filter((item) => item.approval_id !== id),
      );
    } catch (reason: unknown) {
      setActionError(
        reason instanceof Error ? reason.message : t("approvals.actionError"),
      );
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Icon name="approval" size={24} color="var(--procurerpa-blue)" />
        <h1
          className="text-xl font-bold"
          style={{ color: "var(--procurerpa-blue)" }}
        >
          {t("approvals.title")}
        </h1>
        <span
          className="ml-2 rounded-full px-2.5 py-0.5 text-xs font-bold"
          style={{ background: "var(--procurerpa-gold)", color: "white" }}
        >
          {approvals.length}
        </span>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg bg-red-50 p-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}
      {actionError && (
        <div
          role="alert"
          className="rounded-lg bg-red-50 p-3 text-sm text-red-700"
        >
          {actionError}
        </div>
      )}
      {loading && (
        <p className="text-sm" style={{ color: "var(--procurerpa-text-muted)" }}>
          {t("approvals.loading")}
        </p>
      )}

      {!loading && !error && approvals.length === 0 && (
        <GlassCard hoverable={false} padding="lg">
          <div className="flex flex-col items-center justify-center py-12">
            <Icon
              name="check-circle"
              size={48}
              color="var(--status-completed)"
            />
            <p
              className="mt-4 text-sm font-medium"
              style={{ color: "var(--procurerpa-text-secondary)" }}
            >
              {t("approvals.allCaughtUp")}
            </p>
          </div>
        </GlassCard>
      )}

      {!loading &&
        !error &&
        approvals.map((item) => (
          <ApprovalCard
            key={item.approval_id}
            item={item}
            onApprove={(id, note) => handleDecision(id, "approve", note)}
            onReject={(id, note) => handleDecision(id, "reject", note)}
          />
        ))}
    </div>
  );
}
