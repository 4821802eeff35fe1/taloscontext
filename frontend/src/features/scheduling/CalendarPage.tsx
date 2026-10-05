import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { addDays, addMonths, format, isSameDay } from "date-fns";
import { TZDate } from "@date-fns/tz";
import { endpoints, mediaUrl, type CalendarEntry } from "@/lib/api";
import { calendarDays, moveToDay, type CalendarMode } from "@/lib/calendar";
import {
  Button,
  PageHeader,
  ErrorState,
  SkeletonRows,
  Card,
} from "@/components/ui/primitives";
import { DateTimePicker, Segmented, Select } from "@/components/ui/forms";
import { Dialog } from "@/components/ui/overlays";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ContentDetailPanel } from "@/features/content/ContentDetailPanel";
import { toast } from "@/components/ui/toast";
import { dateTime, timezoneOptions } from "@/lib/format";
function Entry({
  entry,
  onClick,
  workspaceId,
}: {
  entry: CalendarEntry;
  workspaceId: string;
  onClick: () => void;
}) {
  const { t } = useTranslation("automation");
  const drag = useDraggable({
    id: entry.id,
    disabled: entry.status !== "SCHEDULED",
  });
  return (
    <div
      ref={drag.setNodeRef}
      className="relative rounded-lg border bg-surface-overlay p-2 text-xs"
      style={
        drag.transform
          ? {
              transform: `translate3d(${drag.transform.x}px,${drag.transform.y}px,0)`,
              zIndex: 20,
            }
          : undefined
      }
    >
      {entry.status === "SCHEDULED" && (
        <button
          {...drag.listeners}
          {...drag.attributes}
          aria-label={`Move ${entry.title}`}
          className="touch-none float-right px-2 cursor-grab text-ink-muted"
        >
          ⠿
        </button>
      )}
      <button onClick={onClick} className="block w-full text-left">
        {entry.media_asset_id && (
          <img
            loading="lazy"
            alt="Post image"
            className="mb-2 h-16 w-full rounded object-cover"
            src={mediaUrl(
              `/api/v1/workspaces/${workspaceId}/media/${entry.media_asset_id}/content`,
            )}
          />
        )}
        <span className="line-clamp-2 font-medium">{entry.title}</span>
        <span className="block text-ink-muted mt-1">
          {entry.channel_set_name} · {entry.category}
        </span>
        <StatusBadge status={entry.status} />
      </button>
    </div>
  );
}
function Day({
  day,
  entries,
  tz,
  onSelect,
  onTime,
  workspaceId,
}: {
  day: Date;
  entries: CalendarEntry[];
  workspaceId: string;
  tz: string;
  onSelect: (id: string) => void;
  onTime: (entry: CalendarEntry) => void;
}) {
  const drop = useDroppable({ id: day.toISOString() });
  return (
    <div
      ref={drop.setNodeRef}
      data-testid="calendar-day"
      data-day={format(day, "yyyy-MM-dd")}
      className={`min-h-40 min-w-0 border p-2 space-y-2 ${drop.isOver ? "bg-accent/15" : "bg-surface-raised"}`}
    >
      <h2 className="text-xs text-ink-muted">{format(day, "EEE d")}</h2>
      {entries.map((e) => (
        <div key={e.id}>
          <Entry
            workspaceId={workspaceId}
            entry={e}
            onClick={() => onSelect(e.id)}
          />
          <div className="flex justify-between mt-1 text-2xs text-ink-faint">
            <span>{dateTime(e.at, tz, "HH:mm")}</span>
            {e.status === "SCHEDULED" && (
              <button onClick={() => onTime(e)}>{t("calendar.changeTime")}</button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
export function CalendarPage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("automation");
  const client = useQueryClient(),
    [anchor, setAnchor] = useState(new Date()),
    [mode, setMode] = useState<CalendarMode>("month"),
    [tz, setTz] = useState(""),
    [target, setTarget] = useState("all"),
    [selected, setSelected] = useState<string | null>(null),
    [moving, setMoving] = useState<CalendarEntry | null>(null),
    [at, setAt] = useState<string | null>(null);
  const settings = useQuery({
    queryKey: ["settings", ws],
    queryFn: () => endpoints.settings(ws),
  });
  const timezone = tz || settings.data?.general.timezone || "UTC";
  const days = calendarDays(anchor, mode, timezone),
    start = days[0].toISOString(),
    end = addDays(days[days.length - 1], 1).toISOString();
  const key = ["calendar", ws, start, end, target];
  const query = useQuery({
    queryKey: key,
    queryFn: () =>
      endpoints.calendar(ws, start, end, target === "all" ? undefined : target),
  });
  const sets = useQuery({
    queryKey: ["channel-sets", ws],
    queryFn: () => endpoints.channelSets(ws),
  });
  const change = useMutation({
    mutationFn: ({ id, at }: { id: string; at: string }) =>
      endpoints.rescheduleContent(ws, id, at),
    onMutate: async ({ id, at }) => {
      await client.cancelQueries({ queryKey: key });
      const previous = client.getQueryData(key);
      client.setQueryData(key, (old: typeof query.data) =>
        old
          ? {
              ...old,
              entries: old.entries.map((e) => (e.id === id ? { ...e, at } : e)),
            }
          : old,
      );
      return { previous };
    },
    onError: (e, _v, context) => {
      client.setQueryData(key, context?.previous);
      toast.error(e.message);
    },
    onSuccess: () => toast.success(t("calendar.rescheduled")),
    onSettled: () => {
      void client.invalidateQueries({
        predicate: (q) => q.queryKey.includes(ws),
      });
    },
  });
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );
  const onDrag = ({ active, over }: DragEndEvent) => {
    if (!over) return;
    const e = query.data?.entries.find((e) => e.id === active.id);
    if (e)
      change.mutate({
        id: e.id,
        at: moveToDay(e.at, new TZDate(String(over.id), timezone), timezone),
      });
  };
  const shift = (n: number) =>
    setAnchor(
      mode === "month"
        ? addMonths(anchor, n)
        : addDays(anchor, n * (mode === "week" ? 7 : 1)),
    );
  return (
    <div className="space-y-4">
      <PageHeader
        title={t("calendar.title")}
        description={t("calendar.description")}
        actions={
          <>
            <Button onClick={() => shift(-1)} aria-label={t("calendar.previousPeriod")}>
              ←
            </Button>
            <Button onClick={() => setAnchor(new Date())}>{t("calendar.today")}</Button>
            <Button onClick={() => shift(1)} aria-label={t("calendar.nextPeriod")}>
              →
            </Button>
          </>
        }
      />
      <div className="flex flex-wrap gap-3 items-center">
        <h2>{format(new TZDate(anchor, timezone), "MMMM yyyy")}</h2>
        <Segmented
          ariaLabel="Calendar mode"
          value={mode}
          onChange={setMode}
          options={[
            { value: "month", label: t("calendar.mode.month") },
            { value: "week", label: t("calendar.mode.week") },
            { value: "day", label: t("calendar.mode.day") },
          ]}
        />
        <Select
          className="w-52"
          ariaLabel="Calendar timezone"
          value={timezone}
          onValueChange={setTz}
          options={timezoneOptions(timezone)}
        />
        <Select
          className="w-52"
          ariaLabel="Calendar target"
          value={target}
          onValueChange={setTarget}
          options={[
            { value: "all", label: t("calendar.allChannelSets") },
            ...(sets.data ?? []).map((s) => ({ value: s.id, label: s.name })),
          ]}
        />
      </div>
      {query.isPending ? (
        <SkeletonRows rows={8} />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : (
        <DndContext sensors={sensors} onDragEnd={onDrag}>
          <div
            className={
              mode === "day"
                ? "grid grid-cols-1"
                : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-7"
            }
          >
            {days.map((day) => (
              <Day
                workspaceId={ws}
                key={day.toISOString()}
                day={day}
                tz={timezone}
                entries={query.data.entries.filter((e) =>
                  isSameDay(new TZDate(e.at, timezone), day),
                )}
                onSelect={setSelected}
                onTime={(e) => {
                  setMoving(e);
                  setAt(e.at);
                }}
              />
            ))}
          </div>
        </DndContext>
      )}
      {!!query.data?.free_slots.length && (
        <Card className="p-4">
          <h2 className="font-medium mb-2">{t("calendar.nextFreeSlots")}</h2>
          <div className="flex flex-wrap gap-2">
            {query.data.free_slots.slice(0, 12).map((s, i) => (
              <span
                className="rounded bg-surface-overlay px-2 py-1 text-xs"
                key={i}
              >
                {s.schedule_name} · {dateTime(s.at, timezone)}
              </span>
            ))}
          </div>
        </Card>
      )}
      <Dialog
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
        title={t("calendar.contentStudio")}
        size="xl"
      >
        {selected && (
          <ContentDetailPanel
            key={selected}
            workspaceId={ws}
            contentId={selected}
          />
        )}
      </Dialog>
      <Dialog
        open={!!moving}
        onOpenChange={(open) => !open && setMoving(null)}
        title={t("calendar.reschedulePost")}
      >
        <DateTimePicker value={at} onChange={setAt} timeZone={timezone} />
        <Button
          className="mt-3"
          disabled={!at || change.isPending}
          onClick={() => {
            change.mutate({ id: moving!.id, at: at! });
            setMoving(null);
          }}
        >
          Save new time
        </Button>
      </Dialog>
    </div>
  );
}
