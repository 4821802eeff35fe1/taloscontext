import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
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
import { ctaKeyLabel, statusLabel } from "@/i18n/labels";
export function ChannelsPage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("channels");
  const [editing, setEditing] = useState<Channel | null>(null);
  const query = useQuery({
      queryKey: ["channels", ws],
      queryFn: () => endpoints.channels(ws),
    }),
    action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader title={t("channels.title")} />
      {query.isPending ? (
        <SkeletonRows />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.length ? (
        <EmptyState
          title={t("channels.empty.title")}
          description={t("channels.empty.description")}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {query.data.map((c) => (
            <Card className="p-4 space-y-3" key={c.id}>
              <div className="flex justify-between gap-2">
                <h2 className="min-w-0 break-words">{c.title}</h2>
                <StatusBadge status={c.health} domain="channel" />
              </div>
              <p className="text-xs text-ink-faint">
                {c.username ? "@" + c.username : t("channels.private")} ·{" "}
                {c.subscriber_count == null
                  ? t("channels.subscribersUnknown")
                  : t("common:count.subscribers", { count: c.subscriber_count })}
              </p>
              <p className="text-xs">
                {c.account_label} · {statusLabel(c.account_status, "account")}
              </p>
              <p className="text-xs text-ink-muted">
                {t("channels.last", { time: c.last_published_at ? dateTime(c.last_published_at, c.timezone) : t("common:state.never") })} ·{" "}
                {t("channels.next", { time: c.next_scheduled_at ? dateTime(c.next_scheduled_at, c.timezone) : t("common:state.none") })} ·{" "}
                {t("channels.posts30d", { count: c.posts_30d })}
              </p>
              <div className="flex flex-wrap justify-between gap-2">
                <label className="flex gap-2 items-center">
                  <Switch
                    label={t("channels.autopilotFor", { title: c.title })}
                    checked={c.autopilot_enabled}
                    onCheckedChange={(autopilot_enabled) =>
                      action.mutate(() =>
                        endpoints.updateChannel(ws, c.id, {
                          autopilot_enabled,
                        }),
                      )
                    }
                  />
                  {t("channels.autopilot")}
                </label>
                <Button onClick={() => setEditing(c)}>{t("channels.settings")}</Button>
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
  const { t } = useTranslation("channels");
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
      title={t("channels.editor.title", { title: c.title })}
    >
      <div className="space-y-3">
        <Select
          ariaLabel={t("channels.editor.tone")}
          value={tone}
          onValueChange={setTone}
          options={[
            { value: "none", label: t("channels.editor.workspaceDefault") },
            ...(tones.data ?? []).map((p) => ({ value: p.id, label: p.name })),
          ]}
        />
        <Select
          ariaLabel={t("channels.editor.timezone")}
          value={tz}
          onValueChange={setTz}
          options={timezoneOptions(tz)}
        />
        {settings.data?.general.cta_keys.map((k) => (
          <Field key={k} label={ctaKeyLabel(k)}>
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
          {t("channels.editor.save")}
        </Button>
      </div>
    </Dialog>
  );
}
