import { useQuery } from "@tanstack/react-query";
import { endpoints, type PostBrief } from "@/lib/api";
import {
  Card,
  StatTile,
  PageHeader,
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "@/components/ui/primitives";
import { AppLink } from "@/components/ui/AppLink";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { rub, dateTime } from "@/lib/format";
function Posts({ title, items }: { title: string; items: PostBrief[] }) {
  return (
    <Card className="p-4">
      <h2 className="mb-3 font-medium">{title}</h2>
      {!items.length ? (
        <EmptyState title="No posts yet" />
      ) : (
        items.map((p) => (
          <AppLink
            to={`/content?post=${p.content_id}`}
            key={p.content_id}
            className="block border-t py-3 text-sm"
          >
            <div className="flex justify-between gap-2">
              <span>{p.title}</span>
              <StatusBadge status={p.status} />
            </div>
            <p className="text-xs text-ink-muted mt-1">
              {dateTime(p.at)} · {p.channel_set_name} · {p.published}/
              {p.targets} delivered · {p.views} views
            </p>
          </AppLink>
        ))
      )}
    </Card>
  );
}
export function DashboardPage({ workspaceId: ws }: { workspaceId: string }) {
  const query = useQuery({
    queryKey: ["dashboard", ws],
    queryFn: () => endpoints.dashboard(ws),
    refetchInterval: 30000,
  });
  const costs = useQuery({
    queryKey: ["costs", ws],
    queryFn: () => endpoints.costDashboard(ws),
  });
  if (query.isPending) return <SkeletonRows rows={8} />;
  if (query.isError)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  const d = query.data;
  return (
    <div className="space-y-5">
      <PageHeader
        title="Overview"
        description="Your channel network at a glance."
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
        {[
          ["Channels", d.channels],
          ["Accounts", d.accounts],
          ["Posts today", d.posts_today],
          ["Scheduled", d.scheduled],
          ["Pending approval", d.pending_approval],
          ["Failed (7d)", d.failed_publications_7d + d.failed_jobs_7d],
        ].map(([label, value]) => (
          <StatTile key={label} label={String(label)} value={value} />
        ))}
      </div>
      {costs.data && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatTile label="AI today" value={rub(costs.data.today_rub)} />
          <StatTile
            label="Month / budget"
            value={rub(costs.data.month_rub)}
            sub={`of ${rub(costs.data.month_budget_rub)}`}
          />
          <StatTile
            label="Month forecast"
            value={rub(costs.data.forecast_month_end_rub)}
          />
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Posts title="Next scheduled" items={d.next_scheduled} />
        <Posts title="Recently published" items={d.recent_published} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="font-medium mb-3">Recent failures</h2>
          {d.recent_failed.length ? (
            d.recent_failed.map((p, i) => (
              <AppLink
                key={i}
                to={`/content?post=${p.content_id}`}
                className="block border-t py-3"
              >
                <p>
                  {p.title} · {p.channel_title}
                </p>
                <p className="text-xs text-danger">{p.error}</p>
              </AppLink>
            ))
          ) : (
            <EmptyState title="No publication failures" />
          )}
        </Card>
        <Card className="p-4 space-y-3">
          <h2 className="font-medium">System health</h2>
          {Object.entries(d.system).map(([name, check]) => (
            <div className="flex justify-between" key={name}>
              <span>{name}</span>
              <span className={check.ok ? "text-success" : "text-warning"}>
                {check.ok ? "Online" : check.error || "Unavailable"}
              </span>
            </div>
          ))}
          <p className="text-xs text-ink-muted">
            AI: {d.ai_provider.text} · Image: {d.ai_provider.image_status}
          </p>
          {d.telegram_accounts.map((a) => (
            <div className="flex justify-between" key={a.id}>
              <span>{a.phone}</span>
              <StatusBadge status={a.status} />
            </div>
          ))}
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="font-medium mb-3">Views · last 7 publish days</h2>
          {d.has_metrics ? (
            <div className="flex h-40 items-end gap-2">
              {d.views_7d.map((day) => (
                <div
                  key={day.day}
                  className="flex flex-1 flex-col items-center justify-end h-full gap-1"
                >
                  <span className="text-xs">{day.views}</span>
                  <div
                    className="w-full rounded-t bg-accent/60"
                    style={{
                      height: `${Math.max(2, (day.views / Math.max(1, ...d.views_7d.map((x) => x.views))) * 110)}px`,
                    }}
                  />
                  <span className="text-2xs">{day.day.slice(5)}</span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No metrics yet"
              description="Metrics appear after publishing and the first refresh."
            />
          )}
        </Card>
        <Posts title="Top posts" items={d.top_posts} />
      </div>
    </div>
  );
}
