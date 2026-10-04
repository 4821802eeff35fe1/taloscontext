import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, type ContentItem } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DistributionPanel } from "@/features/distributions/DistributionPanel";

function TelegramPreview({ html }: { html: string }) {
  return (
    <div className="rounded-xl border border-surface-border bg-[#0e1621] p-4">
      <div
        className="whitespace-pre-wrap text-sm leading-relaxed text-[#e4ecf2] [&_a]:text-[#6ab3f3] [&_b]:font-semibold [&_blockquote]:border-l-2 [&_blockquote]:border-[#6ab3f3] [&_blockquote]:pl-2 [&_code]:rounded [&_code]:bg-black/30 [&_code]:px-1 [&_i]:italic"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}

export function ContentDetailPanel({ workspaceId, contentId }: { workspaceId: string; contentId: string }) {
  const client = useQueryClient();
  const { data: item } = useQuery({
    queryKey: ["content-item", workspaceId, contentId],
    queryFn: () => endpoints.contentDetail(workspaceId, contentId),
  });

  const [title, setTitle] = useState("");
  const [html, setHtml] = useState("");
  const [scheduleAt, setScheduleAt] = useState("");

  useEffect(() => {
    if (item) {
      setTitle(item.title);
      setHtml(item.telegram_html);
    }
  }, [item?.id]);

  const invalidate = () => {
    client.invalidateQueries({ queryKey: ["content-item", workspaceId, contentId] });
    client.invalidateQueries({ queryKey: ["content", workspaceId] });
  };

  const save = useMutation({
    mutationFn: () =>
      endpoints.editContent(workspaceId, contentId, { title, telegram_html: html, plain_text: stripHtml(html) }),
    onSuccess: invalidate,
  });
  const submit = useMutation({ mutationFn: () => endpoints.submitContent(workspaceId, contentId), onSuccess: invalidate });
  const approve = useMutation({ mutationFn: () => endpoints.approveContent(workspaceId, contentId), onSuccess: invalidate });
  const reject = useMutation({ mutationFn: () => endpoints.rejectContent(workspaceId, contentId), onSuccess: invalidate });
  const schedule = useMutation({
    mutationFn: () => endpoints.scheduleContent(workspaceId, contentId, new Date(scheduleAt).toISOString()),
    onSuccess: invalidate,
  });

  if (!item) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-ink-faint">{item.category || "uncategorized"}</p>
          <h2 className="text-lg font-semibold text-ink">{item.title || "Untitled"}</h2>
        </div>
        <StatusBadge status={item.status} />
      </div>

      {item.duplicate_score != null && item.duplicate_score >= 0.6 && (
        <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
          Duplicate risk: {Math.round(item.duplicate_score * 100)}% similar to recent content.
        </div>
      )}
      {item.requires_review && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          Flagged for manual review before publishing.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="space-y-3">
          <div>
            <label className="label">Title</label>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label className="label">Telegram HTML</label>
            <textarea
              className="input min-h-[180px] font-mono text-xs"
              value={html}
              onChange={(e) => setHtml(e.target.value)}
            />
          </div>
          <button className="btn-secondary" onClick={() => save.mutate()} disabled={save.isPending}>
            Save changes
          </button>
        </Card>

        <div className="space-y-3">
          <label className="label">Telegram preview</label>
          <TelegramPreview html={html} />
        </div>
      </div>

      <Card className="flex flex-wrap items-center gap-2">
        {item.status === "DRAFT" && (
          <button className="btn-secondary" onClick={() => submit.mutate()}>
            Submit for approval
          </button>
        )}
        {item.status === "PENDING_APPROVAL" && (
          <>
            <button className="btn-primary" onClick={() => approve.mutate()}>
              Approve
            </button>
            <button className="btn-danger" onClick={() => reject.mutate()}>
              Reject
            </button>
          </>
        )}
        {item.status === "APPROVED" && (
          <div className="flex items-center gap-2">
            <input
              type="datetime-local"
              className="input w-56"
              value={scheduleAt}
              onChange={(e) => setScheduleAt(e.target.value)}
            />
            <button className="btn-primary" onClick={() => schedule.mutate()} disabled={!scheduleAt}>
              Schedule
            </button>
          </div>
        )}
      </Card>

      <DistributionPanel workspaceId={workspaceId} contentId={contentId} />
    </div>
  );
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]+>/g, "");
}

export type { ContentItem };
