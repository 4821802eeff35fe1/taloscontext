import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints, type Channel } from "@/lib/api";
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SkeletonRows,
  Button,
  Input,
  Field,
} from "@/components/ui/primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Select, Switch } from "@/components/ui/forms";
import { Dialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";
import { dateTime, timezoneOptions } from "@/lib/format";
export function ChannelsPage({ workspaceId: ws }: { workspaceId: string }) {
  const [editing, setEditing] = useState<Channel | null>(null);
  const query = useQuery({
      queryKey: ["channels", ws],
      queryFn: () => endpoints.channels(ws),
    }),
    action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader title="Channels" />
      {query.isPending ? (
        <SkeletonRows />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.length ? (
        <EmptyState
          title="No channels imported"
          description="Connect an account and refresh its channels."
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {query.data.map((c) => (
            <Card className="p-4 space-y-3" key={c.id}>
              <div className="flex justify-between gap-2">
                <h2>{c.title}</h2>
                <StatusBadge status={c.health} />
              </div>
              <p className="text-xs text-ink-faint">
                {c.username ? "@" + c.username : "Private"} ·{" "}
                {c.subscriber_count ?? "—"} subscribers
              </p>
              <p className="text-xs">
                {c.account_label} · {c.account_status}
              </p>
              <p className="text-xs text-ink-muted">
                Last {dateTime(c.last_published_at, c.timezone)} · Next{" "}
                {dateTime(c.next_scheduled_at, c.timezone)} · {c.posts_30d}{" "}
                posts/30d
              </p>
              <div className="flex justify-between">
                <label className="flex gap-2 items-center">
                  <Switch
                    label={`Autopilot ${c.title}`}
                    checked={c.autopilot_enabled}
                    onCheckedChange={(autopilot_enabled) =>
                      action.mutate(() =>
                        endpoints.updateChannel(ws, c.id, {
                          autopilot_enabled,
                        }),
                      )
                    }
                  />
                  Autopilot
                </label>
                <Button onClick={() => setEditing(c)}>Settings</Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing && (
        <ChannelEditor
          key={editing.id}
          ws={ws}
          c={editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
function ChannelEditor({
  ws,
  c,
  onClose,
}: {
  ws: string;
  c: Channel;
  onClose: () => void;
}) {
  const [tone, setTone] = useState(c.tone_profile_id ?? "none"),
    [tz, setTz] = useState(c.timezone),
    [cta, setCta] = useState(c.cta_overrides);
  const tones = useQuery({
      queryKey: ["tones", ws],
      queryFn: () => endpoints.toneProfiles(ws),
    }),
    settings = useQuery({
      queryKey: ["settings", ws],
      queryFn: () => endpoints.settings(ws),
    });
  const action = useOperation(ws, async () => {
    await endpoints.updateChannel(ws, c.id, {
      tone_profile_id: tone === "none" ? null : tone,
      clear_tone_profile: tone === "none",
      timezone: tz,
      cta_overrides: cta,
    });
    onClose();
  });
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={c.title + " settings"}
    >
      <div className="space-y-3">
        <Select
          ariaLabel="Channel tone"
          value={tone}
          onValueChange={setTone}
          options={[
            { value: "none", label: "Workspace default" },
            ...(tones.data ?? []).map((t) => ({ value: t.id, label: t.name })),
          ]}
        />
        <Select
          ariaLabel="Channel timezone"
          value={tz}
          onValueChange={setTz}
          options={timezoneOptions(tz)}
        />
        {settings.data?.general.cta_keys.map((k) => (
          <Field key={k} label={k}>
            <Input
              value={cta[k] ?? ""}
              onChange={(e) => setCta({ ...cta, [k]: e.target.value })}
            />
          </Field>
        ))}
        <Button
          variant="primary"
          loading={action.isPending}
          onClick={() => action.mutate()}
        >
          Save channel
        </Button>
      </div>
    </Dialog>
  );
}
