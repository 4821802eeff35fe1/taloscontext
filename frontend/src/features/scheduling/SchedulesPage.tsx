import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { dateTime, timezoneOptions } from "@/lib/format";
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
        title="Schedules"
        description="Local time windows become persistent UTC publication times."
        actions={
          <Button variant="primary" onClick={() => setEditing(null)}>
            Create schedule
          </Button>
        }
      />
      {query.isPending ? (
        <SkeletonRows />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.length ? (
        <EmptyState
          title="No schedules"
          description="Define posting windows for a channel set."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {query.data.map((s) => (
            <Card key={s.id} className="p-4 space-y-3">
              <div className="flex justify-between">
                <h2 className="font-medium">{s.name}</h2>
                <Switch
                  label={`Enable ${s.name}`}
                  checked={s.enabled}
                  onCheckedChange={(v) =>
                    action.mutate(() => endpoints.pauseSchedule(ws, s.id, !v))
                  }
                />
              </div>
              <p className="text-sm text-ink-muted">
                {s.channel_set_name || "Any target"} · {s.posts_per_day}{" "}
                posts/day · {s.timezone}
              </p>
              <p className="text-xs">
                {s.windows.map((w) => w.start + "–" + w.end).join(" · ")} ·{" "}
                {s.randomize ? "Random" : "Fixed"}
              </p>
              <p className="text-xs text-ink-faint">
                {s.next_slots
                  .slice(0, 3)
                  .map((at) => dateTime(at, s.timezone))
                  .join(" · ")}
              </p>
              <div className="flex gap-2">
                <Button onClick={() => setEditing(s)}>Edit</Button>
                <Button variant="danger" onClick={() => setRemove(s.id)}>
                  Delete
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
        title="Delete this schedule?"
        description="Existing scheduled posts keep their times."
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
    "Preview updated",
  );
  const field = <K extends keyof ScheduleInput>(
    key: K,
    value: ScheduleInput[K],
  ) => setDraft({ ...draft, [key]: value });
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={schedule ? "Edit schedule" : "Create schedule"}
      size="lg"
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate();
        }}
      >
        <Field label="Name" htmlFor="schedule-name">
          <Input
            id="schedule-name"
            value={draft.name}
            required
            onChange={(e) => field("name", e.target.value)}
          />
        </Field>
        <Select
          ariaLabel="Schedule target"
          value={draft.channel_set_id ?? "none"}
          onValueChange={(v) =>
            field("channel_set_id", v === "none" ? null : v)
          }
          options={[
            { value: "none", label: "Any channel set" },
            ...(sets.data ?? []).map((s) => ({ value: s.id, label: s.name })),
          ]}
        />
        <Select
          ariaLabel="Schedule timezone"
          value={draft.timezone}
          onValueChange={(v) => field("timezone", v)}
          options={timezoneOptions(draft.timezone)}
        />
        <div className="flex flex-wrap gap-3">
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) => (
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
        <div className="grid grid-cols-3 gap-3">
          {(
            [
              "posts_per_day",
              "min_interval_minutes",
              "max_posts_per_day",
            ] as const
          ).map((f) => (
            <Field label={f.replaceAll("_", " ")} key={f}>
              <Input
                aria-label={f}
                type="number"
                min={f === "min_interval_minutes" ? 0 : 1}
                value={draft[f]}
                onChange={(e) => field(f, Number(e.target.value))}
              />
            </Field>
          ))}
        </div>
        <Field label="Time windows">
          {draft.windows.map((w, i) => (
            <div className="flex items-center gap-2 mb-2" key={i}>
              <Input
                aria-label={`Window ${i + 1} start`}
                value={w.start}
                placeholder="HH:MM"
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
                aria-label={`Window ${i + 1} end`}
                value={w.end}
                placeholder="HH:MM"
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
                aria-label="Remove window"
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
            Add window
          </Button>
        </Field>
        <label className="flex gap-2 items-center">
          <Switch
            label="Randomized times"
            checked={draft.randomize}
            onCheckedChange={(v) => field("randomize", v)}
          />
          Randomized inside windows
        </label>
        <Field label="Categories">
          <TagInput
            ariaLabel="Schedule categories"
            value={draft.categories}
            onChange={(v) => field("categories", v)}
          />
        </Field>
        <Field label="Excluded dates (YYYY-MM-DD)">
          <TagInput
            ariaLabel="Excluded dates"
            value={draft.exclude_dates}
            onChange={(v) => field("exclude_dates", v)}
          />
        </Field>
        <Select
          ariaLabel="Misfire policy"
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
                ? "Workspace policy"
                : value.replaceAll("_", " "),
          }))}
        />
        <div className="flex gap-2">
          <Button onClick={() => preview.mutate()} loading={preview.isPending}>
            Preview slots
          </Button>
          <Button type="submit" variant="primary" loading={action.isPending}>
            Save schedule
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
