import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, type Schedule, type ScheduleInput } from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  SkeletonRows,
} from "@/components/ui/primitives";
import { Checkbox, Select, Switch, TagInput } from "@/components/ui/forms";
import { ConfirmDialog, Dialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";
import { dateTime, timezoneOptions, weekdayNames } from "@/lib/format";
import { misfirePolicyLabel } from "@/i18n/labels";
const defaults: ScheduleInput = {
  name: "",
  channel_set_id: null,
  timezone: "Europe/Moscow",
  days_of_week: [0, 1, 2, 3, 4, 5, 6],
  posts_per_day: 3,
  windows: [
    { start: "11:00", end: "13:00" },
    { start: "16:00", end: "18:00" },
    { start: "20:00", end: "22:00" },
  ],
  randomize: true,
  min_interval_minutes: 60,
  max_posts_per_day: 10,
  categories: [],
  exclude_dates: [],
  enabled: true,
  misfire_policy: null,
};
export function SchedulesPage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("automation");
  const [editing, setEditing] = useState<Schedule | null | undefined>(
      undefined,
    ),
    [remove, setRemove] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["schedules", ws],
    queryFn: () => endpoints.schedules(ws),
  });
  const action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader
        title={t("schedules.title")}
        description={t("schedules.description")}
        actions={
          <Button variant="primary" onClick={() => setEditing(null)}>
            {t("schedules.create")}
          </Button>
        }
      />
      {query.isPending ? (
        <SkeletonRows />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.length ? (
        <EmptyState
          title={t("schedules.empty.title")}
          description={t("schedules.empty.description")}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {query.data.map((s) => (
            <Card key={s.id} className="p-4 space-y-3">
              <div className="flex justify-between gap-2">
                <h2 className="min-w-0 break-words font-medium">{s.name}</h2>
                <Switch
                  label={t("schedules.enable", { name: s.name })}
                  checked={s.enabled}
                  onCheckedChange={(v) =>
                    action.mutate(() => endpoints.pauseSchedule(ws, s.id, !v))
                  }
                />
              </div>
              <p className="text-sm text-ink-muted">
                {s.channel_set_name || t("schedules.anyTarget")} ·{" "}
                {t("common:count.postsPerDay", { count: s.posts_per_day })} · {s.timezone}
              </p>
              <p className="text-xs">
                {s.windows.map((w) => w.start + "–" + w.end).join(" · ")} ·{" "}
                {s.randomize ? t("schedules.random") : t("schedules.fixed")}
              </p>
              <p className="text-xs text-ink-faint">
                {s.next_slots
                  .slice(0, 3)
                  .map((at) => dateTime(at, s.timezone))
                  .join(" · ")}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => setEditing(s)}>{t("common:action.edit")}</Button>
                <Button variant="danger" onClick={() => setRemove(s.id)}>
                  {t("common:action.delete")}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing !== undefined && (
        <ScheduleEditor
          key={editing?.id || "new"}
          ws={ws}
          schedule={editing}
          onClose={() => setEditing(undefined)}
        />
      )}
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(open) => !open && setRemove(null)}
        title={t("schedules.deleteConfirm")}
        description={t("schedules.deleteHint")}
        destructive
        onConfirm={() => {
          action.mutate(() => endpoints.deleteSchedule(ws, remove!));
          setRemove(null);
        }}
      />
    </div>
  );
}
function ScheduleEditor({
  ws,
  schedule,
  onClose,
}: {
  ws: string;
  schedule: Schedule | null;
  onClose: () => void;
}) {
  const { t } = useTranslation("automation");
  const [draft, setDraft] = useState<ScheduleInput>(schedule ?? defaults),
    [slots, setSlots] = useState<string[]>([]);
  const sets = useQuery({
    queryKey: ["channel-sets", ws],
    queryFn: () => endpoints.channelSets(ws),
  });
  const action = useOperation(ws, async () => {
    if (schedule) await endpoints.updateSchedule(ws, schedule.id, draft);
    else await endpoints.createSchedule(ws, draft);
    onClose();
  });
  const preview = useOperation(
    ws,
    async () => setSlots(await endpoints.previewSchedule(ws, draft)),
    t("schedules.previewUpdated"),
  );
  const field = <K extends keyof ScheduleInput>(
    key: K,
    value: ScheduleInput[K],
  ) => setDraft({ ...draft, [key]: value });
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={schedule ? t("schedules.editTitle") : t("schedules.create")}
      size="lg"
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate();
        }}
      >
        <Field label={t("schedules.name")} htmlFor="schedule-name">
          <Input
            id="schedule-name"
            value={draft.name}
            required
            onChange={(e) => field("name", e.target.value)}
          />
        </Field>
        <Select
          ariaLabel={t("schedules.target")}
          value={draft.channel_set_id ?? "none"}
          onValueChange={(v) =>
            field("channel_set_id", v === "none" ? null : v)
          }
          options={[
            { value: "none", label: t("schedules.anySet") },
            ...(sets.data ?? []).map((s) => ({ value: s.id, label: s.name })),
          ]}
        />
        <Select
          ariaLabel={t("schedules.timezone")}
          value={draft.timezone}
          onValueChange={(v) => field("timezone", v)}
          options={timezoneOptions(draft.timezone)}
        />
        <div className="flex flex-wrap gap-3">
          {weekdayNames().map((d, i) => (
            <label key={d} className="flex gap-1 items-center">
              <Checkbox
                label={d}
                checked={draft.days_of_week.includes(i)}
                onCheckedChange={(v) =>
                  field(
                    "days_of_week",
                    v
                      ? [...draft.days_of_week, i]
                      : draft.days_of_week.filter((x) => x !== i),
                  )
                }
              />
              {d}
            </label>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {(
            [
              "posts_per_day",
              "min_interval_minutes",
              "max_posts_per_day",
            ] as const
          ).map((f) => (
            <Field label={t(`schedules.field.${f}`)} key={f}>
              <Input
                aria-label={t(`schedules.field.${f}`)}
                type="number"
                min={f === "min_interval_minutes" ? 0 : 1}
                value={draft[f]}
                onChange={(e) => field(f, Number(e.target.value))}
              />
            </Field>
          ))}
        </div>
        <Field label={t("schedules.windows")}>
          {draft.windows.map((w, i) => (
            <div className="flex items-center gap-2 mb-2" key={i}>
              <Input
                aria-label={t("schedules.windowStart", { n: i + 1 })}
                value={w.start}
                placeholder={t("schedules.timePlaceholder")}
                onChange={(e) =>
                  field(
                    "windows",
                    draft.windows.map((x, j) =>
                      j === i ? { ...x, start: e.target.value } : x,
                    ),
                  )
                }
              />
              <span>–</span>
              <Input
                aria-label={t("schedules.windowEnd", { n: i + 1 })}
                value={w.end}
                placeholder={t("schedules.timePlaceholder")}
                onChange={(e) =>
                  field(
                    "windows",
                    draft.windows.map((x, j) =>
                      j === i ? { ...x, end: e.target.value } : x,
                    ),
                  )
                }
              />
              <Button
                aria-label={t("schedules.removeWindow")}
                onClick={() =>
                  field(
                    "windows",
                    draft.windows.filter((_, j) => j !== i),
                  )
                }
              >
                ×
              </Button>
            </div>
          ))}
          <Button
            onClick={() =>
              field("windows", [
                ...draft.windows,
                { start: "09:00", end: "10:00" },
              ])
            }
          >
            {t("schedules.addWindow")}
          </Button>
        </Field>
        <label className="flex gap-2 items-center">
          <Switch
            label={t("schedules.randomized")}
            checked={draft.randomize}
            onCheckedChange={(v) => field("randomize", v)}
          />
          {t("schedules.randomizedHint")}
        </label>
        <Field label={t("schedules.categories")}>
          <TagInput
            ariaLabel={t("schedules.categories")}
            value={draft.categories}
            onChange={(v) => field("categories", v)}
          />
        </Field>
        <Field label={t("schedules.excluded")}>
          <TagInput
            ariaLabel={t("schedules.excludedLabel")}
            placeholder={t("schedules.excludedPlaceholder")}
            value={draft.exclude_dates}
            onChange={(v) => field("exclude_dates", v)}
          />
        </Field>
        <Select
          ariaLabel={t("schedules.misfire")}
          value={draft.misfire_policy ?? "default"}
          onValueChange={(v) =>
            field("misfire_policy", v === "default" ? null : v)
          }
          options={[
            "default",
            "SKIP",
            "PUBLISH_IMMEDIATELY",
            "RESCHEDULE_NEXT_SLOT",
          ].map((value) => ({
            value,
            label:
              value === "default"
                ? t("schedules.workspacePolicy")
                : misfirePolicyLabel(value),
          }))}
        />
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => preview.mutate()} loading={preview.isPending}>
            {t("schedules.preview")}
          </Button>
          <Button type="submit" variant="primary" loading={action.isPending}>
            {t("schedules.save")}
          </Button>
        </div>
        {!!slots.length && (
          <p className="text-xs text-ink-muted">
            {slots.map((s) => dateTime(s, draft.timezone)).join(" · ")}
          </p>
        )}
      </form>
    </Dialog>
  );
}
