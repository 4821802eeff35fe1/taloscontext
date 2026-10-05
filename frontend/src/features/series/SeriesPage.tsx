import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, type Series, type SeriesInput } from "@/lib/api";
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
import { Select } from "@/components/ui/forms";
import { Dialog, ConfirmDialog } from "@/components/ui/overlays";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { AppLink } from "@/components/ui/AppLink";
import { useOperation } from "@/hooks/useOperations";
const initial: SeriesInput = {
  title: "",
  description: "",
  channel_set_id: null,
  tone_profile_id: null,
  schedule_id: null,
  category: "educational",
  status: "DRAFT",
  numbering_format: "#{n:03d}",
  planned_topics: [],
};
export function SeriesPage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("automation");
  const [editing, setEditing] = useState<Series | null | undefined>(),
    [selected, setSelected] = useState<Series | null>(null),
    [remove, setRemove] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["series", ws],
    queryFn: () => endpoints.series(ws),
  });
  const action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader
        title={t("series.title")}
        description={t("series.description")}
        actions={
          <Button variant="primary" onClick={() => setEditing(null)}>
            Create series
          </Button>
        }
      />
      {query.isPending ? (
        <SkeletonRows />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.length ? (
        <EmptyState title={t("series.emptyTitle")} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {query.data.map((s) => (
            <Card className="p-4 space-y-3" key={s.id}>
              <div className="flex justify-between">
                <h2>{s.title}</h2>
                <StatusBadge status={s.status} />
              </div>
              <p className="text-sm text-ink-muted">{s.description}</p>
              <p className="text-xs">
                {s.published_count} published · {s.planned_count} planned ·
                Next: {s.next_label} {s.next_topic}
              </p>
              <progress
                className="w-full accent-accent"
                max={Math.max(1, s.planned_count)}
                value={s.published_count}
                aria-label={t("series.progressAria")}
              />
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => setEditing(s)}>{t("series.edit")}</Button>
                <Button onClick={() => setSelected(s)}>{t("series.viewParts")}</Button>
                <Button
                  disabled={["PAUSED", "COMPLETED"].includes(s.status)}
                  onClick={() =>
                    action.mutate(() =>
                      endpoints.generateContent(ws, { series_id: s.id }),
                    )
                  }
                >
                  Generate next part
                </Button>
                <Button variant="danger" onClick={() => setRemove(s.id)}>
                  Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing !== undefined && (
        <SeriesEditor
          ws={ws}
          series={editing}
          onClose={() => setEditing(undefined)}
        />
      )}
      <Dialog
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
        title={selected?.title || "Parts"}
      >
        {[...(selected?.items ?? []), ...(selected?.in_progress ?? [])].map(
          (p) => (
            <AppLink
              key={p.content_id}
              to={`/content?post=${p.content_id}`}
              className="block border-b py-3"
            >
              {p.label} {p.title} · {p.status}
            </AppLink>
          ),
        )}
      </Dialog>
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(open) => !open && setRemove(null)}
        title={t("series.deleteTitle")}
        destructive
        onConfirm={() => {
          action.mutate(() => endpoints.deleteSeries(ws, remove!));
          setRemove(null);
        }}
      />
    </div>
  );
}
function SeriesEditor({
  ws,
  series,
  onClose,
}: {
  ws: string;
  series: Series | null;
  onClose: () => void;
}) {
  const [d, setD] = useState<SeriesInput>(series ?? initial);
  const sets = useQuery({
      queryKey: ["channel-sets", ws],
      queryFn: () => endpoints.channelSets(ws),
    }),
    tones = useQuery({
      queryKey: ["tones", ws],
      queryFn: () => endpoints.toneProfiles(ws),
    }),
    schedules = useQuery({
      queryKey: ["schedules", ws],
      queryFn: () => endpoints.schedules(ws),
    });
  const action = useOperation(ws, async () => {
    if (series) await endpoints.updateSeries(ws, series.id, d);
    else await endpoints.createSeries(ws, d);
    onClose();
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={t("series.dialogTitle")} size="lg">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate();
        }}
      >
        {(
          ["title", "description", "category", "numbering_format"] as const
        ).map((k) => (
          <Field key={k} label={k.replaceAll("_", " ")}>
            <Input
              aria-label={k}
              value={d[k]}
              required={k === "title"}
              onChange={(e) => setD({ ...d, [k]: e.target.value })}
            />
          </Field>
        ))}
        <Select
          ariaLabel="Series status"
          value={d.status}
          onValueChange={(v) => setD({ ...d, status: v })}
          options={["DRAFT", "ACTIVE", "PAUSED", "COMPLETED"].map((value) => ({
            value,
            label: value,
          }))}
        />
        {(
          [
            {
              field: "channel_set_id",
              label: t("series.target"),
              options: sets.data?.map((s) => ({ value: s.id, label: s.name })),
            },
            {
              field: "tone_profile_id",
              label: t("series.tone"),
              options: tones.data?.map((s) => ({ value: s.id, label: s.name })),
            },
            {
              field: "schedule_id",
              label: t("series.schedule"),
              options: schedules.data?.map((s) => ({
                value: s.id,
                label: s.name,
              })),
            },
          ] as const
        ).map((f) => (
          <Select
            key={f.field}
            ariaLabel={f.label}
            value={d[f.field] ?? "none"}
            onValueChange={(v) =>
              setD({ ...d, [f.field]: v === "none" ? null : v })
            }
            options={[
              { value: "none", label: `${t("series.nonePrefix")} ${f.label.toLowerCase()}` },
              ...(f.options ?? []),
            ]}
          />
        ))}
        <Field label={t("series.plannedTopics")}>
          <Textarea
            aria-label={t("series.plannedTopicsAria")}
            value={d.planned_topics.join("\n")}
            onChange={(e) =>
              setD({ ...d, planned_topics: e.target.value.split("\n") })
            }
          />
        </Field>
        <Button type="submit" variant="primary" loading={action.isPending}>
          Save series
        </Button>
      </form>
    </Dialog>
  );
}
