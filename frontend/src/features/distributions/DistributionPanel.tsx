import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, ApiError } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";

/** Per-channel delivery status for one ContentItem: "8 / 10 published" + retry of failed only. */
export function DistributionPanel({
  workspaceId,
  contentId,
}: {
  workspaceId: string;
  contentId: string;
}) {
  const client = useQueryClient();
  const [resolution, setResolution] = useState<{
    id: string;
    outcome: "published" | "failed";
  } | null>(null);
  const resolve = useOperation(
    workspaceId,
    (value: { id: string; outcome: "published" | "failed" }) =>
      endpoints.resolvePublication(workspaceId, value.id, value.outcome),
  );
  const batches = useQuery({
    queryKey: ["batches", workspaceId, contentId],
    queryFn: () => endpoints.batches(workspaceId, contentId),
    // Poll only while something is still in flight.
    refetchInterval: (q) =>
      q.state.data?.some(
        (b) => b.status === "PUBLISHING" || b.status === "PENDING",
      )
        ? 4000
        : false,
  });
  const channels = useQuery({
    queryKey: ["channels", workspaceId],
    queryFn: () => endpoints.channels(workspaceId),
  });
  const channelName = (id: string) => {
    const c = channels.data?.find((ch) => ch.id === id);
    return c ? (c.username ? `@${c.username}` : c.title) : id.slice(0, 8);
  };

  const retry = useMutation({
    mutationFn: (batchId: string) => endpoints.retryBatch(workspaceId, batchId),
    onSuccess: () => {
      client.invalidateQueries({
        queryKey: ["batches", workspaceId, contentId],
      });
      client.invalidateQueries({
        queryKey: ["content-item", workspaceId, contentId],
      });
    },
  });

  if (!batches.data || batches.data.length === 0) return null;

  return (
    <div className="space-y-3">
      {batches.data.map((batch) => {
        const total = batch.publications.length;
        const ok = batch.publications.filter(
          (p) => p.status === "SUCCESS",
        ).length;
        const failed = batch.publications.filter(
          (p) => p.status === "FAILED" && !p.delivery_unknown,
        ).length;
        return (
          <Card key={batch.id} className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-ink">
                  Distribution
                </span>
                <StatusBadge status={batch.status} />
              </div>
              <span className="text-sm text-ink-muted">
                {ok} / {total} published
              </span>
            </div>

            <div className="divide-y divide-surface-border rounded-lg border border-surface-border">
              {batch.publications.map((p) => (
                <div
                  key={p.id}
                  className="flex flex-wrap gap-2 items-center justify-between px-3 py-2 text-sm"
                >
                  <span className="text-ink">{channelName(p.channel_id)}</span>
                  <div className="flex items-center gap-3">
                    {p.error_message && (
                      <span
                        className="max-w-[260px] truncate text-xs text-danger"
                        title={p.error_message}
                      >
                        {p.error_message}
                      </span>
                    )}
                    <StatusBadge
                      status={
                        p.delivery_unknown ? "DELIVERY_UNKNOWN" : p.status
                      }
                    />
                    {p.delivery_unknown && (
                      <div className="flex flex-wrap gap-2">
                        <button
                          className="btn-secondary"
                          onClick={() =>
                            setResolution({ id: p.id, outcome: "published" })
                          }
                        >
                          Confirm published
                        </button>
                        <button
                          className="btn-secondary"
                          onClick={() =>
                            setResolution({ id: p.id, outcome: "failed" })
                          }
                        >
                          Confirm not delivered
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {failed > 0 && (
              <div className="flex items-center gap-3">
                <button
                  className="btn-secondary"
                  onClick={() => retry.mutate(batch.id)}
                  disabled={retry.isPending}
                >
                  Retry {failed} failed
                </button>
                <span className="text-xs text-ink-faint">
                  Succeeded channels are never re-sent.
                </span>
                {retry.error && (
                  <span className="text-xs text-danger">
                    {retry.error instanceof ApiError
                      ? retry.error.message
                      : "Retry failed"}
                  </span>
                )}
              </div>
            )}
          </Card>
        );
      })}
      <ConfirmDialog
        open={!!resolution}
        onOpenChange={(open) => !open && setResolution(null)}
        title="Resolve uncertain delivery?"
        description="Check the actual Telegram channel first. Confirming not delivered allows a later retry; confirming published prevents another send."
        onConfirm={() => {
          resolve.mutate(resolution!);
          setResolution(null);
        }}
      />
    </div>
  );
}
