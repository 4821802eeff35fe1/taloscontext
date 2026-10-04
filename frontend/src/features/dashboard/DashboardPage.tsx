import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { StatTile, Card, EmptyState } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { AppLink } from "@/components/ui/AppLink";

export function DashboardPage({ workspaceId }: { workspaceId: string }) {
  const channels = useQuery({ queryKey: ["channels", workspaceId], queryFn: () => endpoints.channels(workspaceId) });
  const accounts = useQuery({
    queryKey: ["telegram-accounts", workspaceId],
    queryFn: () => endpoints.telegramAccounts(workspaceId),
  });
  const content = useQuery({ queryKey: ["content", workspaceId], queryFn: () => endpoints.content(workspaceId) });
  const costs = useQuery({ queryKey: ["costs", workspaceId], queryFn: () => endpoints.costDashboard(workspaceId) });
  const jobs = useQuery({ queryKey: ["jobs", workspaceId], queryFn: () => endpoints.jobs(workspaceId) });

  const postsToday = content.data?.filter((c) => c.published_at?.startsWith(new Date().toISOString().slice(0, 10))).length ?? 0;
  const scheduled = content.data?.filter((c) => c.status === "SCHEDULED").length ?? 0;
  const pendingApproval = content.data?.filter((c) => c.status === "PENDING_APPROVAL").length ?? 0;
  const failedJobs = jobs.data?.filter((j) => j.status === "FAILED").length ?? 0;

  const monthPct = costs.data
    ? Math.min(100, (parseFloat(costs.data.month_rub) / Math.max(1, parseFloat(costs.data.month_budget_rub))) * 100)
    : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-ink">Overview</h1>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Managed channels" value={channels.data?.length ?? "—"} />
        <StatTile label="Connected accounts" value={accounts.data?.filter((a) => a.status === "CONNECTED").length ?? "—"} />
        <StatTile label="Posts today" value={postsToday} />
        <StatTile label="Scheduled" value={scheduled} />
        <StatTile label="Pending approval" value={pendingApproval} />
        <StatTile label="Failed jobs" value={failedJobs} />
      </div>

      {costs.data && (
        <Card>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-ink">AI spend this month</span>
            <span className="text-sm text-ink-muted">
              {costs.data.month_rub} ₽ / {costs.data.month_budget_rub} ₽
            </span>
          </div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-surface-overlay">
            <div
              className="h-full rounded-full bg-accent"
              style={{ width: `${monthPct}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-ink-faint">
            Forecast at current pace: {costs.data.forecast_month_end_rub} ₽ by month end · Today: {costs.data.today_rub} ₽
          </p>
        </Card>
      )}

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-medium text-ink">Recent posts</span>
          <AppLink to="/content" className="text-xs text-accent hover:underline">
            View all
          </AppLink>
        </div>
        {content.data && content.data.length > 0 ? (
          <div className="divide-y divide-surface-border">
            {content.data.slice(0, 6).map((item) => (
              <div key={item.id} className="flex items-center justify-between py-2.5">
                <div>
                  <p className="text-sm text-ink">{item.title || item.topic || "Untitled"}</p>
                  <p className="text-xs text-ink-faint">{item.category || "uncategorized"}</p>
                </div>
                <StatusBadge status={item.status} />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No content yet"
            description="Generate your first AI post to see it here."
            action={
              <AppLink to="/content" className="btn-primary">
                Create post
              </AppLink>
            }
          />
        )}
      </Card>
    </div>
  );
}
