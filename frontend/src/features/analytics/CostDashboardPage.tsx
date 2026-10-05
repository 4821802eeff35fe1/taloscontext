import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, type Named } from "@/lib/api";
import {
  Card,
  PageHeader,
  StatTile,
  ErrorState,
  SkeletonRows,
  EmptyState,
} from "@/components/ui/primitives";
import { AppLink } from "@/components/ui/AppLink";
import { categoryLabel } from "@/i18n/labels";
import { number, percent, rub } from "@/lib/format";

export function BudgetBar({
  spent,
  budget,
  warning = 80,
}: {
  spent: string;
  budget: string;
  warning?: number;
}) {
  const { t } = useTranslation("analytics");
  const pct =
    Number(budget) > 0
      ? (Number(spent) / Number(budget)) * 100
      : Number(spent) > 0
        ? 100
        : 0;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap justify-between gap-2 text-xs">
        <span>
          {t("budget.spentOf", { spent: rub(spent), budget: rub(budget) })}
        </span>
        <span>{percent(pct / 100)}</span>
      </div>
      <div
        role="progressbar"
        aria-label={t("budget.usage")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(100, pct)}
        className="h-2 overflow-hidden rounded bg-surface-overlay"
      >
        <div
          className={
            pct >= 100
              ? "h-full bg-danger"
              : pct >= warning
                ? "h-full bg-warning"
                : "h-full bg-accent"
          }
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
    </div>
  );
}

export function CostDashboardPage({
  workspaceId: ws,
}: {
  workspaceId: string;
}) {
  const { t } = useTranslation("analytics");
  const query = useQuery({
    queryKey: ["costs", ws],
    queryFn: () => endpoints.costDashboard(ws),
  });
  if (query.isPending) return <SkeletonRows />;
  if (query.isError)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  const d = query.data;
  // Rows keep the API's machine keys; only labels are localized here.
  const groups: [string, Named[], (row: Named) => string][] = [
    ["breakdown", d.breakdown, (row) => t(`costs.kind.${row.key}`, { defaultValue: row.label })],
    ["byChannelSet", d.by_channel_set, (row) => (row.key === "none" ? t("costs.noTarget") : row.label)],
    ["byCategory", d.by_category, (row) => (row.key === "none" ? t("costs.noCategory") : categoryLabel(row.key))],
    ["byProvider", d.by_provider, (row) => row.label],
  ];
  return (
    <div className="space-y-5">
      <PageHeader title={t("costs.title")} description={t("costs.description")} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          ["today", d.today_rub],
          ["week", d.week_rub],
          ["month", d.month_rub],
          ["forecast", d.forecast_month_end_rub],
        ].map(([key, value]) => (
          <StatTile key={key} label={t(`costs.tile.${key}`)} value={rub(value)} />
        ))}
      </div>
      <Card className="space-y-3 p-4">
        <h2>{t("costs.monthlyBudget")}</h2>
        <BudgetBar spent={d.month_rub} budget={d.month_budget_rub} warning={d.warning_pct} />
        <p className="text-xs text-ink-muted">
          {t("costs.tokens", {
            input: number(d.input_tokens_month),
            output: number(d.output_tokens_month),
          })}
        </p>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        {groups.map(([key, rows, label]) => (
          <Card className="p-4" key={key}>
            <h2 className="mb-3 font-medium">{t(`costs.group.${key}`)}</h2>
            {rows.map((row) => (
              <div key={row.key} className="flex justify-between gap-3 border-t py-2 text-sm">
                <span className="min-w-0 truncate">
                  {label(row)} · {t("common:count.requests", { count: row.requests })}
                </span>
                <span className="shrink-0">{rub(row.cost_rub)}</span>
              </div>
            ))}
            {!rows.length && <EmptyState title={t("costs.noUsage")} />}
          </Card>
        ))}
      </div>
      <Card className="p-4">
        <h2 className="mb-3 font-medium">{t("costs.topContent")}</h2>
        {d.top_content.map((p) => (
          <AppLink
            to={`/content?post=${p.content_id}`}
            className="flex justify-between gap-3 border-t py-2"
            key={p.content_id}
          >
            <span className="min-w-0 truncate">
              {p.title || t("common:untitled")} · {t("common:count.requests", { count: p.requests })}
            </span>
            <span className="shrink-0">{rub(p.cost_rub)}</span>
          </AppLink>
        ))}
        {!d.top_content.length && <EmptyState title={t("costs.noUsage")} />}
      </Card>
    </div>
  );
}
