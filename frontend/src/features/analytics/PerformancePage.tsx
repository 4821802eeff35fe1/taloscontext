import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints } from "@/lib/api";
import { Card, EmptyState, ErrorState, PageHeader, SkeletonRows } from "@/components/ui/primitives";
import { Segmented } from "@/components/ui/forms";
import { number } from "@/lib/format";

const PERIODS = ["7", "30", "90"] as const;

/** Per-channel publication metrics from the latest snapshot of each post. */
export function PerformancePage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("analytics");
  const [days, setDays] = useState<(typeof PERIODS)[number]>("30");
  const query = useQuery({
    queryKey: ["performance", ws, days],
    queryFn: () => endpoints.performance(ws, Number(days)),
  });
  const rows = query.data ?? [];
  const totals = rows.reduce(
    (acc, r) => ({ posts: acc.posts + r.posts, views: acc.views + r.views, forwards: acc.forwards + r.forwards, reactions: acc.reactions + r.reactions }),
    { posts: 0, views: 0, forwards: 0, reactions: 0 },
  );
  return (
    <div className="space-y-5">
      <PageHeader
        title={t("performance.title")}
        description={t("performance.description")}
        actions={
          <Segmented
            ariaLabel={t("performance.period")}
            value={days}
            onChange={setDays}
            options={PERIODS.map((p) => ({ value: p, label: t("performance.days", { count: Number(p) }) }))}
          />
        }
      />
      <Card className="overflow-x-auto">
        {query.isPending ? (
          <SkeletonRows />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !rows.length ? (
          <EmptyState title={t("performance.empty.title")} description={t("performance.empty.description")} />
        ) : (
          <table className="w-full min-w-[560px] text-sm">
            <thead className="text-left text-xs text-ink-faint">
              <tr>
                <th className="p-3 font-medium">{t("performance.col.channel")}</th>
                <th className="p-3 text-right font-medium">{t("performance.col.posts")}</th>
                <th className="p-3 text-right font-medium">{t("performance.col.views")}</th>
                <th className="p-3 text-right font-medium">{t("performance.col.forwards")}</th>
                <th className="p-3 text-right font-medium">{t("performance.col.reactions")}</th>
                <th className="p-3 text-right font-medium">{t("performance.col.avgViews")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.channel_id} className="border-t">
                  <td className="p-3">{r.channel_title}</td>
                  <td className="p-3 text-right tabular-nums">{number(r.posts)}</td>
                  <td className="p-3 text-right tabular-nums">{number(r.views)}</td>
                  <td className="p-3 text-right tabular-nums">{number(r.forwards)}</td>
                  <td className="p-3 text-right tabular-nums">{number(r.reactions)}</td>
                  <td className="p-3 text-right tabular-nums">{number(r.posts ? r.views / r.posts : 0)}</td>
                </tr>
              ))}
              <tr className="border-t font-medium">
                <td className="p-3">{t("performance.total")}</td>
                <td className="p-3 text-right tabular-nums">{number(totals.posts)}</td>
                <td className="p-3 text-right tabular-nums">{number(totals.views)}</td>
                <td className="p-3 text-right tabular-nums">{number(totals.forwards)}</td>
                <td className="p-3 text-right tabular-nums">{number(totals.reactions)}</td>
                <td className="p-3 text-right tabular-nums">{number(totals.posts ? totals.views / totals.posts : 0)}</td>
              </tr>
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
