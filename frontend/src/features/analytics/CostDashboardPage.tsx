import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import {
  Card,
  PageHeader,
  StatTile,
  ErrorState,
  SkeletonRows,
  EmptyState,
} from "@/components/ui/primitives";
import { rub } from "@/lib/format";
export function BudgetBar({
  spent,
  budget,
  warning = 80,
}: {
  spent: string;
  budget: string;
  warning?: number;
}) {
  const pct =
    Number(budget) > 0
      ? (Number(spent) / Number(budget)) * 100
      : Number(spent) > 0
        ? 100
        : 0;
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs">
        <span>
          {rub(spent)} / {rub(budget)}
        </span>
        <span>{pct.toFixed(0)}%</span>
      </div>
      <div
        role="progressbar"
        aria-label="Budget usage"
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
  return (
    <div className="space-y-5">
      <PageHeader
        title="AI costs"
        description="Recorded usage and configured rates for every AI attempt."
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          ["Today", d.today_rub],
          ["7 days", d.week_rub],
          ["Month", d.month_rub],
          ["Forecast", d.forecast_month_end_rub],
        ].map(([label, value]) => (
          <StatTile key={label} label={label} value={rub(value)} />
        ))}
      </div>
      <Card className="p-4 space-y-3">
        <h2>Monthly budget</h2>
        <BudgetBar
          spent={d.month_rub}
          budget={d.month_budget_rub}
          warning={d.warning_pct}
        />
        <p className="text-xs text-ink-muted">
          {d.input_tokens_month.toLocaleString()} input tokens ·{" "}
          {d.output_tokens_month.toLocaleString()} output tokens
        </p>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        {[
          ["Spend breakdown", d.breakdown],
          ["By channel set", d.by_channel_set],
          ["By category", d.by_category],
          ["By provider", d.by_provider],
        ].map(([label, rows]) => (
          <Card className="p-4" key={String(label)}>
            <h2 className="font-medium mb-3">{String(label)}</h2>
            {typeof rows !== "string" &&
              rows.map((row) => (
                <div
                  key={row.key}
                  className="flex justify-between border-t py-2 text-sm"
                >
                  <span>
                    {row.label} · {row.requests} calls
                  </span>
                  <span>{rub(row.cost_rub)}</span>
                </div>
              ))}
            {typeof rows !== "string" && !rows.length && (
              <EmptyState title="No usage yet" />
            )}
          </Card>
        ))}
      </div>
      <Card className="p-4">
        <h2 className="font-medium mb-3">Most expensive content</h2>
        {d.top_content.map((p) => (
          <div
            className="flex justify-between border-t py-2"
            key={p.content_id}
          >
            <span>
              {p.title} · {p.requests} calls
            </span>
            <span>{rub(p.cost_rub)}</span>
          </div>
        ))}
      </Card>
    </div>
  );
}
