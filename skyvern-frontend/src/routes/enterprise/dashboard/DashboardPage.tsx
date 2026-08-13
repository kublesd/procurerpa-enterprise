import { useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import { GlassCard } from "@/components/enterprise/GlassCard";
import { RiskBadge } from "@/components/enterprise/RiskBadge";
import { StatusBadge } from "@/components/enterprise/StatusBadge";
import { Icon } from "@/components/Icon";
import { useI18n } from "@/i18n/useI18n";
import { authFetch } from "@/util/authFetch";

type OverviewData = {
  total_tasks: number;
  completed_tasks: number;
  active_tasks: number;
  failed_tasks: number;
  canceled_tasks: number;
  pending_approvals: number;
  total_quotes: number;
  success_rate_30d: number;
};

type TrendItem = {
  date: string;
  completed: number;
  failed: number;
  total: number;
};

type CategoryItem = {
  category_id: string;
  category_name: string;
  total_tasks: number;
  completed_tasks: number;
  total_quotes: number;
  success_rate: number;
};

type RecentTask = {
  task_id: string;
  title: string | null;
  status: string;
  department_id: string;
  category_id: string | null;
  category_name: string;
  risk_level: string;
  created_at: string;
};

async function fetchJson<T>(path: string): Promise<T> {
  const response = await authFetch(path);
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Keep the status when the server did not return JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function EmptyState() {
  const { t } = useI18n();
  return (
    <p
      data-testid="dashboard-empty"
      className="py-10 text-center text-sm"
      style={{ color: "var(--procurerpa-text-muted)" }}
    >
      {t("dashboard.noData")}
    </p>
  );
}

function OverviewCards({ data }: { data: OverviewData }) {
  const { t } = useI18n();
  const cards = [
    {
      label: t("dashboard.totalTasks"),
      value: data.total_tasks,
      icon: "task" as const,
      color: "var(--procurerpa-blue)",
    },
    {
      label: t("dashboard.completedTasks"),
      value: data.completed_tasks,
      icon: "check-circle" as const,
      color: "var(--status-completed)",
    },
    {
      label: t("dashboard.pendingApproval"),
      value: data.pending_approvals,
      icon: "clock" as const,
      color: "var(--procurerpa-gold)",
    },
    {
      label: t("dashboard.quoteCount"),
      value: data.total_quotes,
      icon: "audit" as const,
      color: "var(--status-needs-human)",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <GlassCard key={card.label} padding="md" hoverable={false}>
          <div className="flex items-center justify-between">
            <div>
              <p
                className="text-xs font-medium uppercase tracking-wider"
                style={{ color: "var(--procurerpa-text-muted)" }}
              >
                {card.label}
              </p>
              <p
                className="mt-1 text-2xl font-bold"
                style={{ color: "var(--procurerpa-text-primary)" }}
              >
                {card.value.toLocaleString()}
              </p>
            </div>
            <div
              className="flex h-12 w-12 items-center justify-center rounded-xl"
              style={{ background: `${card.color}10` }}
            >
              <Icon name={card.icon} size={24} color={card.color} />
            </div>
          </div>
        </GlassCard>
      ))}
    </div>
  );
}

function TrendChart({ data }: { data: TrendItem[] }) {
  const { t } = useI18n();
  const option = {
    tooltip: { trigger: "axis" as const },
    legend: {
      data: [t("dashboard.chartCompleted"), t("dashboard.chartFailed")],
      bottom: 0,
    },
    grid: { left: 45, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: "category" as const,
      data: data.map((item) => item.date.slice(5)),
    },
    yAxis: { type: "value" as const, minInterval: 1 },
    series: [
      {
        name: t("dashboard.chartCompleted"),
        type: "line",
        smooth: true,
        data: data.map((item) => item.completed),
        itemStyle: { color: "#10B981" },
      },
      {
        name: t("dashboard.chartFailed"),
        type: "line",
        smooth: true,
        data: data.map((item) => item.failed),
        itemStyle: { color: "#EF4444" },
      },
    ],
  };
  return <ReactECharts option={option} style={{ height: 300 }} />;
}

function CategoryTable({ data }: { data: CategoryItem[] }) {
  const { t } = useI18n();
  return (
    <table className="w-full text-sm">
      <thead>
        <tr style={{ borderBottom: "1px solid var(--glass-border)" }}>
          <th className="pb-3 text-left font-medium">
            {t("dashboard.category")}
          </th>
          <th className="pb-3 text-right font-medium">
            {t("dashboard.totalTasksShort")}
          </th>
          <th className="pb-3 text-right font-medium">
            {t("dashboard.quoteCount")}
          </th>
          <th className="pb-3 text-right font-medium">
            {t("dashboard.successRateLabel")}
          </th>
        </tr>
      </thead>
      <tbody>
        {data.map((item) => (
          <tr
            key={item.category_id}
            style={{ borderBottom: "1px solid var(--glass-border)" }}
          >
            <td
              className="py-3"
              style={{ color: "var(--procurerpa-text-primary)" }}
            >
              {item.category_name}
            </td>
            <td
              className="py-3 text-right"
              style={{ color: "var(--procurerpa-text-secondary)" }}
            >
              {item.total_tasks}
            </td>
            <td
              className="py-3 text-right"
              style={{ color: "var(--procurerpa-text-secondary)" }}
            >
              {item.total_quotes}
            </td>
            <td
              className="py-3 text-right font-medium"
              style={{ color: "var(--procurerpa-text-primary)" }}
            >
              {item.success_rate}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RecentTasksTable({ data }: { data: RecentTask[] }) {
  const { t } = useI18n();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr style={{ borderBottom: "1px solid var(--glass-border)" }}>
            <th className="pb-3 text-left font-medium">
              {t("dashboard.taskName")}
            </th>
            <th className="pb-3 text-left font-medium">
              {t("dashboard.status")}
            </th>
            <th className="pb-3 text-left font-medium">
              {t("dashboard.category")}
            </th>
            <th className="pb-3 text-left font-medium">
              {t("dashboard.risk")}
            </th>
            <th className="pb-3 text-right font-medium">
              {t("dashboard.createdAt")}
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((task) => (
            <tr
              key={task.task_id}
              style={{ borderBottom: "1px solid var(--glass-border)" }}
            >
              <td className="py-3">
                <a
                  className="font-medium underline"
                  href={`/tasks/${task.task_id}/diagnostics`}
                  style={{ color: "var(--procurerpa-blue)" }}
                >
                  {task.title || task.task_id}
                </a>
                <div
                  className="text-xs"
                  style={{ color: "var(--procurerpa-text-muted)" }}
                >
                  {task.task_id}
                </div>
              </td>
              <td className="py-3">
                <StatusBadge status={task.status} />
              </td>
              <td
                className="py-3"
                style={{ color: "var(--procurerpa-text-secondary)" }}
              >
                {task.category_name}
              </td>
              <td className="py-3">
                <RiskBadge level={task.risk_level} />
              </td>
              <td
                className="py-3 text-right text-xs"
                style={{ color: "var(--procurerpa-text-muted)" }}
              >
                {new Date(task.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DashboardPage() {
  const { t } = useI18n();
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [trend, setTrend] = useState<TrendItem[]>([]);
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [recentTasks, setRecentTasks] = useState<RecentTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchJson<OverviewData>("/api/v1/enterprise/dashboard/overview"),
      fetchJson<TrendItem[]>("/api/v1/enterprise/dashboard/trend?days=30"),
      fetchJson<CategoryItem[]>("/api/v1/enterprise/dashboard/categories"),
      fetchJson<{ items: RecentTask[] }>(
        "/api/v1/enterprise/dashboard/recent-tasks?limit=10",
      ),
    ])
      .then(([nextOverview, nextTrend, nextCategories, nextRecent]) => {
        if (!active) return;
        setOverview(nextOverview);
        setTrend(nextTrend);
        setCategories(nextCategories);
        setRecentTasks(nextRecent.items);
      })
      .catch((reason: unknown) => {
        if (active)
          setError(
            reason instanceof Error ? reason.message : t("dashboard.loadError"),
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [t]);

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Icon name="dashboard" size={24} color="var(--procurerpa-blue)" />
          <h1
            className="text-xl font-bold"
            style={{ color: "var(--procurerpa-blue)" }}
          >
            {t("dashboard.title")}
          </h1>
        </div>
        {overview && (
          <span
            className="rounded-full px-3 py-1 text-xs font-medium"
            style={{
              background: "rgba(16,185,129,0.1)",
              color: "var(--status-completed)",
            }}
          >
            {t("dashboard.successRate30d")}: {overview.success_rate_30d}%
          </span>
        )}
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
          {t("dashboard.loading")}
        </p>
      )}

      {overview && <OverviewCards data={overview} />}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <GlassCard hoverable={false} padding="md">
          <h2
            className="mb-4 text-sm font-semibold"
            style={{ color: "var(--procurerpa-text-primary)" }}
          >
            {t("dashboard.taskTrend30")}
          </h2>
          {trend.length ? <TrendChart data={trend} /> : <EmptyState />}
        </GlassCard>
        <GlassCard hoverable={false} padding="md">
          <h2
            className="mb-4 text-sm font-semibold"
            style={{ color: "var(--procurerpa-text-primary)" }}
          >
            {t("dashboard.categories")}
          </h2>
          {categories.length ? (
            <CategoryTable data={categories} />
          ) : (
            <EmptyState />
          )}
        </GlassCard>
      </div>

      <GlassCard hoverable={false} padding="md">
        <h2
          className="mb-4 text-sm font-semibold"
          style={{ color: "var(--procurerpa-text-primary)" }}
        >
          {t("dashboard.recentTasks")}
        </h2>
        {recentTasks.length ? (
          <RecentTasksTable data={recentTasks} />
        ) : (
          <EmptyState />
        )}
      </GlassCard>
    </div>
  );
}
