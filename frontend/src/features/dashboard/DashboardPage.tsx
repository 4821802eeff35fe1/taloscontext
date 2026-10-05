import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { errorLabel, knownError, statusLabel } from "@/i18n/labels";
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
import { rub, dateTime, number, calendarDate } from "@/lib/format";
function Posts({ title, items }: { title: string; items: PostBrief[] }) {
  const { t } = useTranslation("dashboard");
  return (
    <Card className="p-4">
      <h2 className="mb-3 font-medium">{title}</h2>
      {!items.length ? (
        <EmptyState title={t("noPosts")} />
      ) : (
        items.map((p) => (
          <AppLink
            to={`/content?post=${p.content_id}`}
            key={p.content_id}
            className="block border-t py-3 text-sm"
          >
            <div className="flex justify-between gap-2">
              <span className="min-w-0 truncate">{p.title || t("common:untitled")}</span>
              <StatusBadge status={p.status} domain="content" />
            </div>
            <p className="text-xs text-ink-muted mt-1">
              {[
                dateTime(p.at),
                p.channel_set_name,
                t("delivered", { ok: p.published, total: p.targets }),
                t("common:count.views", { count: p.views }),
              ].filter(Boolean).join(" · ")}
            </p>
          </AppLink>
        ))
      )}
    </Card>
  );
}
export function DashboardPage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("dashboard");
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
        title={t("title")}
        description={t("description")}
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
        {[
          ["channels", d.channels],
          ["accounts", d.accounts],
          ["postsToday", d.posts_today],
          ["scheduled", d.scheduled],
          ["pendingApproval", d.pending_approval],
          ["failed7d", d.failed_publications_7d + d.failed_jobs_7d],
        ].map(([key, value]) => (
          <StatTile key={key} label={t(`tile.${key}`)} value={number(value as number)} />
        ))}
      </div>
      {costs.data && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatTile label={t("tile.aiToday")} value={rub(costs.data.today_rub)} />
          <StatTile
            label={t("tile.monthBudget")}
            value={rub(costs.data.month_rub)}
            sub={t("ofBudget", { budget: rub(costs.data.month_budget_rub) })}
          />
          <StatTile
            label={t("tile.forecast")}
            value={rub(costs.data.forecast_month_end_rub)}
          />
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Posts title={t("nextScheduled")} items={d.next_scheduled} />
        <Posts title={t("recentlyPublished")} items={d.recent_published} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="font-medium mb-3">{t("recentFailures")}</h2>
          {d.recent_failed.length ? (
            d.recent_failed.map((p, i) => (
              <AppLink
                key={i}
                to={`/content?post=${p.content_id}`}
                className="block border-t py-3"
              >
                <p>
                  {p.title || t("common:untitled")} · {p.channel_title}
                </p>
                <p className="text-xs text-danger">
                  {knownError(p.error_code) ? errorLabel(p.error_code!, { channel: p.channel_title, seconds: 0 }) : p.error}
                </p>
              </AppLink>
            ))
          ) : (
            <EmptyState title={t("noFailures")} />
          )}
        </Card>
        <Card className="p-4 space-y-3">
          <h2 className="font-medium">{t("systemHealth")}</h2>
          {Object.entries(d.system).map(([name, check]) => (
            <div className="flex justify-between gap-2" key={name}>
              <span>{t(`service.${name}`, { defaultValue: name })}</span>
              <span className={check.ok ? "text-success" : "text-warning"} title={check.error}>
                {check.ok ? t("online") : t("unavailable")}
              </span>
            </div>
          ))}
          <p className="text-xs text-ink-muted">
            {t("aiProviders", { text: d.ai_provider.text, image: statusLabel(d.ai_provider.image_status, "provider") })}
          </p>
          {d.telegram_accounts.map((a) => (
            <div className="flex justify-between" key={a.id}>
              <span>{a.phone}</span>
              <StatusBadge status={a.status} domain="account" />
            </div>
          ))}
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="font-medium mb-3">{t("views7d")}</h2>
          {d.has_metrics ? (
            <div className="flex h-40 items-end gap-2">
              {d.views_7d.map((day) => (
                <div
                  key={day.day}
                  className="flex flex-1 flex-col items-center justify-end h-full gap-1"
                >
                  <span className="text-xs">{number(day.views)}</span>
                  <div
                    className="w-full rounded-t bg-accent/60"
                    style={{
                      height: `${Math.max(2, (day.views / Math.max(1, ...d.views_7d.map((x) => x.views))) * 110)}px`,
                    }}
                  />
                  <span className="text-2xs">{calendarDate(new Date(`${day.day}T12:00:00`), "weekday-day")}</span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title={t("noMetrics.title")}
              description={t("noMetrics.description")}
            />
          )}
        </Card>
        <Posts title={t("topPosts")} items={d.top_posts} />
      </div>
    </div>
  );
}
