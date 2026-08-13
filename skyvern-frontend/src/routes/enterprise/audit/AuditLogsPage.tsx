import { useEffect, useState } from "react";
import { GlassCard } from "@/components/enterprise/GlassCard";
import { StatusBadge } from "@/components/enterprise/StatusBadge";
import { Timeline, type TimelineItem } from "@/components/enterprise/Timeline";
import { ScreenshotDiff } from "@/components/enterprise/ScreenshotDiff";
import { Icon } from "@/components/Icon";
import { useI18n } from "@/i18n/useI18n";
import { authFetch } from "@/util/authFetch";

type AuditLogEntry = {
  audit_log_id: string;
  task_id: string;
  action_index: number;
  action_type: string;
  target_element: string | null;
  input_value: string | null;
  page_url: string | null;
  screenshot_before_url: string | null;
  screenshot_after_url: string | null;
  duration_ms: number | null;
  executor: string;
  execution_result: string;
  error_message: string | null;
  has_approval: boolean;
  created_at: string;
};

type TaskGroup = {
  task_id: string;
  logs: AuditLogEntry[];
};

type AuditLogResponse = {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
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

function groupByTask(logs: AuditLogEntry[]): TaskGroup[] {
  const groups = new Map<string, AuditLogEntry[]>();
  for (const log of logs)
    groups.set(log.task_id, [...(groups.get(log.task_id) ?? []), log]);
  return Array.from(groups, ([task_id, groupedLogs]) => ({
    task_id,
    logs: groupedLogs,
  }));
}

function LogTimelineItem({
  log,
  expanded,
  onToggle,
}: {
  log: AuditLogEntry;
  expanded: boolean;
  onToggle: () => void;
}) {
  const timelineItem: TimelineItem = {
    id: log.audit_log_id,
    title: `#${log.action_index} ${log.action_type}`,
    description: `${log.target_element ?? ""}${log.input_value ? ` → ${log.input_value}` : ""}${log.duration_ms != null ? ` (${log.duration_ms}ms)` : ""}`,
    timestamp: new Date(log.created_at).toLocaleTimeString(),
    status: log.execution_result === "success" ? "success" : "error",
  };

  return (
    <div>
      <div className="cursor-pointer" onClick={onToggle}>
        <Timeline items={[timelineItem]} />
      </div>
      {expanded && (log.screenshot_before_url || log.screenshot_after_url) && (
        <div className="ml-12 mt-2">
          <ScreenshotDiff
            beforeUrl={log.screenshot_before_url ?? undefined}
            afterUrl={log.screenshot_after_url ?? undefined}
          />
        </div>
      )}
      {expanded && log.error_message && (
        <div className="ml-12 mt-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {log.error_message}
        </div>
      )}
    </div>
  );
}

export function AuditLogsPage() {
  const { t } = useI18n();
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [filterType, setFilterType] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    authFetch("/api/v1/enterprise/audit/logs")
      .then(async (response) => {
        if (!response.ok) throw await responseError(response);
        return response.json() as Promise<AuditLogResponse>;
      })
      .then((data) => {
        if (active) setLogs(data.items);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setLogs([]);
        setError(
          reason instanceof Error ? reason.message : t("audit.loadError"),
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [t]);

  const filteredLogs =
    filterType === "all"
      ? logs
      : logs.filter((log) => log.action_type === filterType);
  const groups = groupByTask(filteredLogs);
  const actionTypes = [...new Set(logs.map((log) => log.action_type))];

  function toggleExpand(id: string) {
    setExpandedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Icon name="audit" size={24} color="var(--procurerpa-blue)" />
          <h1
            className="text-xl font-bold"
            style={{ color: "var(--procurerpa-blue)" }}
          >
            {t("audit.title")}
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <Icon name="filter" size={16} color="var(--procurerpa-text-muted)" />
          <select
            className="glass-input text-sm"
            value={filterType}
            onChange={(event) => setFilterType(event.target.value)}
          >
            <option value="all">{t("audit.allTypes")}</option>
            {actionTypes.map((actionType) => (
              <option key={actionType} value={actionType}>
                {actionType}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg bg-red-50 p-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}
      {loading && (
        <p className="text-sm" style={{ color: "var(--procurerpa-text-muted)" }}>
          {t("audit.loading")}
        </p>
      )}
      {!loading && !error && groups.length === 0 && (
        <GlassCard hoverable={false} padding="lg">
          <p
            className="py-10 text-center text-sm"
            style={{ color: "var(--procurerpa-text-muted)" }}
          >
            {t("audit.noData")}
          </p>
        </GlassCard>
      )}

      {!loading &&
        !error &&
        groups.map((group) => (
          <GlassCard key={group.task_id} hoverable={false} padding="md">
            <div className="mb-4 flex items-center gap-3">
              <Icon name="task" size={20} color="var(--procurerpa-blue)" />
              <h3
                className="text-sm font-semibold"
                style={{ color: "var(--procurerpa-text-primary)" }}
              >
                {t("audit.task")}: {group.task_id}
              </h3>
              <StatusBadge
                status={
                  group.logs.some((log) => log.execution_result !== "success")
                    ? "failed"
                    : "completed"
                }
              />
              <span
                className="text-xs"
                style={{ color: "var(--procurerpa-text-muted)" }}
              >
                {t("audit.actionCount", { count: group.logs.length })}
              </span>
            </div>
            <div className="space-y-2">
              {group.logs.map((log) => (
                <LogTimelineItem
                  key={log.audit_log_id}
                  log={log}
                  expanded={expandedIds.has(log.audit_log_id)}
                  onToggle={() => toggleExpand(log.audit_log_id)}
                />
              ))}
            </div>
          </GlassCard>
        ))}
    </div>
  );
}
