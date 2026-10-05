import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, type ChannelSet, type ChannelSetDetail } from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  SkeletonRows,
  Textarea,
} from "@/components/ui/primitives";
import { Select, Checkbox } from "@/components/ui/forms";
import { Dialog, ConfirmDialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { AppLink } from "@/components/ui/AppLink";
import { channelSetModeLabel, statusLabel } from "@/i18n/labels";
export function SetHealth({ set }: { set: ChannelSet }) {
  const { t } = useTranslation("channels");
  return (
    <span
      className={
        set.healthy_count === set.member_count && set.member_count > 0
          ? "text-success"
          : "text-warning"
      }
    >
      {t("sets.ready", { healthy: set.healthy_count, count: set.member_count })}
    </span>
  );
}
export function ChannelSetsPage({ workspaceId: ws }: { workspaceId: string }) {
  const [editing, setEditing] = useState<ChannelSetDetail | null | undefined>(
      () =>
        new URLSearchParams(window.location.search).has("create")
          ? null
          : undefined,
    ),
    [selected, setSelected] = useState<string | null>(() =>
      new URLSearchParams(window.location.search).get("set"),
    ),
    [remove, setRemove] = useState<string | null>(null);
  const { t } = useTranslation("channels");
  const query = useQuery({
      queryKey: ["channel-sets", ws],
      queryFn: () => endpoints.channelSets(ws),
    }),
    detail = useQuery({
      queryKey: ["channel-set", ws, selected],
      queryFn: () => endpoints.channelSet(ws, selected!),
      enabled: !!selected,
    });
  const action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader
        title={t("sets.title")}
        description={t("sets.description")}
        actions={
          <Button variant="primary" onClick={() => setEditing(null)}>
            {t("sets.new")}
          </Button>
        }
      />
      {query.isPending ? (
        <SkeletonRows />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.length ? (
        <EmptyState title={t("sets.empty")} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {query.data.map((s) => (
            <Card className="p-4 space-y-3" key={s.id}>
              <h2 className="break-words">{s.name}</h2>
              <p className="text-xs text-ink-muted">{s.description}</p>
              <div className="flex flex-wrap justify-between gap-2 text-xs">
                <SetHealth set={s} />
                <span>{channelSetModeLabel(s.mode)}</span>
              </div>
              <Button onClick={() => setSelected(s.id)}>{t("sets.viewDetails")}</Button>
            </Card>
          ))}
        </div>
      )}
      <Dialog
        open={!!selected}
        onOpenChange={(o) => !o && setSelected(null)}
        title={detail.data?.name || t("sets.fallbackTitle")}
        size="lg"
      >
        {detail.isPending ? (
          <SkeletonRows />
        ) : detail.isError ? (
          <ErrorState error={detail.error} />
        ) : (
          detail.data && (
            <div className="space-y-4">
              <SetHealth set={detail.data} />
              <p>
                {t("common:count.subscribers", { count: detail.data.subscribers })} ·{" "}
                {t("common:count.views", { count: detail.data.totals.views })} ·{" "}
                {t("common:count.publications", { count: detail.data.totals.publications })}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() => {
                    setEditing(detail.data!);
                    setSelected(null);
                  }}
                >
                  {t("sets.edit")}
                </Button>
                <Button variant="danger" onClick={() => setRemove(selected)}>
                  {t("common:action.delete")}
                </Button>
              </div>
              {detail.data.channels.map((c) => (
                <p key={c.id}>
                  {c.title} · {c.account_label} · {statusLabel(c.health, "channel")}
                </p>
              ))}
              <h3>{t("sets.recentPosts")}</h3>
              {detail.data.recent_posts.map((p) => (
                <AppLink
                  className="block border-t py-2"
                  key={p.content_id}
                  to={`/content?post=${p.content_id}`}
                >
                  {p.title || t("common:untitled")} <StatusBadge status={p.status} domain="content" />
                </AppLink>
              ))}
            </div>
          )
        )}
      </Dialog>
      {editing !== undefined && (
        <SetEditor
          ws={ws}
          set={editing}
          onClose={() => setEditing(undefined)}
        />
      )}
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(o) => !o && setRemove(null)}
        title={t("sets.deleteConfirm")}
        destructive
        onConfirm={() => {
          action.mutate(async () => {
            await endpoints.deleteChannelSet(ws, remove!);
            setSelected(null);
          });
          setRemove(null);
        }}
      />
    </div>
  );
}
function SetEditor({
  ws,
  set,
  onClose,
}: {
  ws: string;
  set: ChannelSetDetail | null;
  onClose: () => void;
}) {
  const { t } = useTranslation("channels");
  const [name, setName] = useState(set?.name ?? ""),
    [description, setDescription] = useState(set?.description ?? ""),
    [mode, setMode] = useState(set?.mode ?? "EXACT"),
    [selected, setSelected] = useState(set?.channels.map((c) => c.id) ?? []);
  const channels = useQuery({
    queryKey: ["channels", ws],
    queryFn: () => endpoints.channels(ws),
  });
  const action = useOperation(ws, async () => {
    const body = { name, description, mode, channel_ids: selected };
    if (set) await endpoints.updateChannelSet(ws, set.id, body);
    else await endpoints.createChannelSet(ws, body);
    onClose();
  });
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={set ? t("sets.editTitle") : t("sets.createTitle")}
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate();
        }}
      >
        <Field label={t("sets.name")} htmlFor="set-name">
          <Input
            id="set-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Textarea
          aria-label={t("sets.descriptionLabel")}
          placeholder={t("sets.descriptionPlaceholder")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <Select
          ariaLabel={t("sets.mode")}
          value={mode}
          onValueChange={setMode}
          options={["EXACT", "CTA_PER_CHANNEL", "CONTACT_PER_CHANNEL"].map((value) => ({
            value,
            label: t(`mode.${value}.option`),
          }))}
        />
        <div className="max-h-60 overflow-auto space-y-2">
          {channels.data?.map((c) => (
            <label className="flex gap-2 items-center text-sm" key={c.id}>
              <Checkbox
                label={c.title}
                checked={selected.includes(c.id)}
                onCheckedChange={(v) =>
                  setSelected(
                    v
                      ? [...selected, c.id]
                      : selected.filter((x) => x !== c.id),
                  )
                }
              />
              {c.title}
              <span className="text-ink-faint">{statusLabel(c.health, "channel")}</span>
            </label>
          ))}
        </div>
        <Button
          type="submit"
          variant="primary"
          disabled={!selected.length}
          loading={action.isPending}
        >
          {set ? t("sets.save") : t("sets.create")}
        </Button>
      </form>
    </Dialog>
  );
}
