import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { StatTile, Card } from "@/components/ui/Card";

export function CostDashboardPage({ workspaceId }: { workspaceId: string }) {
  const costs = useQuery({ queryKey: ["costs", workspaceId], queryFn: () => endpoints.costDashboard(workspaceId) });
  const aiStatus = useQuery({ queryKey: ["ai-status", workspaceId], queryFn: () => endpoints.aiStatus(workspaceId) });

  if (!costs.data) return null;

  const monthPct = Math.min(100, (parseFloat(costs.data.month_rub) / Math.max(1, parseFloat(costs.data.month_budget_rub))) * 100);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-ink">AI cost dashboard</h1>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Today" value={`${costs.data.today_rub} ₽`} />
        <StatTile label="This month" value={`${costs.data.month_rub} ₽`} />
        <StatTile label="Monthly budget" value={`${costs.data.month_budget_rub} ₽`} />
        <StatTile label="Forecast (month end)" value={`${costs.data.forecast_month_end_rub} ₽`} />
      </div>

      <Card>
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-ink">Monthly budget usage</span>
          <span className="text-ink-muted">{monthPct.toFixed(0)}%</span>
        </div>
        <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-surface-overlay">
          <div
            className={monthPct >= 100 ? "h-full rounded-full bg-danger" : monthPct >= 80 ? "h-full rounded-full bg-warning" : "h-full rounded-full bg-accent"}
            style={{ width: `${monthPct}%` }}
          />
        </div>
      </Card>

      {aiStatus.data && (
        <Card className="space-y-2 text-sm">
          <p className="font-medium text-ink">Provider status</p>
          <p className="text-ink-muted">
            Text: {aiStatus.data.text_provider} {aiStatus.data.text_provider_is_fake && "(fake, dev mode)"}
          </p>
          <p className="text-ink-muted">
            Image: {aiStatus.data.image_provider} — {aiStatus.data.image_provider_status}
            {aiStatus.data.image_provider_is_fake && " (fake, dev mode)"}
          </p>
          {aiStatus.data.image_provider_status === "UNAVAILABLE" && !aiStatus.data.image_provider_is_fake && (
            <p className="text-xs text-ink-faint">
              Image provider is not available through the configured Timeweb API. Text generation and publishing are unaffected.
            </p>
          )}
        </Card>
      )}
    </div>
  );
}
