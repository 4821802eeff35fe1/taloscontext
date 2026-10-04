import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { Card, EmptyState } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import * as Switch from "@radix-ui/react-switch";

export function ChannelsPage({ workspaceId }: { workspaceId: string }) {
  const client = useQueryClient();
  const channels = useQuery({ queryKey: ["channels", workspaceId], queryFn: () => endpoints.channels(workspaceId) });

  const toggleAutopilot = useMutation({
    mutationFn: (vars: { id: string; value: boolean }) =>
      endpoints.updateChannel(workspaceId, vars.id, { autopilot_enabled: vars.value }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["channels", workspaceId] }),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-ink">Channels</h1>

      <Card>
        {channels.data && channels.data.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {channels.data.map((c) => (
              <div key={c.id} className="rounded-lg border border-surface-border p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-ink">{c.title}</p>
                    <p className="text-xs text-ink-faint">{c.username ? `@${c.username}` : "private"}</p>
                  </div>
                  <StatusBadge status={c.health} />
                </div>
                <p className="mt-2 text-xs text-ink-muted">
                  {c.subscriber_count?.toLocaleString() ?? "—"} subscribers
                </p>
                <div className="mt-3 flex items-center justify-between">
                  <span className="text-xs text-ink-muted">Autopilot</span>
                  <Switch.Root
                    checked={c.autopilot_enabled}
                    onCheckedChange={(v) => toggleAutopilot.mutate({ id: c.id, value: v })}
                    className="h-5 w-9 rounded-full bg-surface-overlay data-[state=checked]:bg-accent"
                  >
                    <Switch.Thumb className="block h-4 w-4 translate-x-0.5 rounded-full bg-white transition-transform data-[state=checked]:translate-x-[18px]" />
                  </Switch.Root>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No channels imported yet"
            description="Connect a Telegram account and refresh its channels to see them here."
          />
        )}
      </Card>
    </div>
  );
}
