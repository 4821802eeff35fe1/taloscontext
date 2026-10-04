import * as RadixCheckbox from "@radix-ui/react-checkbox";
import * as RadixSelect from "@radix-ui/react-select";
import * as RadixSwitch from "@radix-ui/react-switch";
import * as RadixTabs from "@radix-ui/react-tabs";
import { TZDate } from "@date-fns/tz";
import {
  addDays,
  addMonths,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import {
  Calendar as CalendarIcon,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  X,
} from "lucide-react";
import { useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { Popover } from "./overlays";
import { Button, cn } from "./primitives";

// ---------------------------------------------------------------- Select

export type Option = {
  value: string;
  label: string;
  hint?: string;
  disabled?: boolean;
};

export function Select({
  value,
  onValueChange,
  options,
  placeholder = "Select…",
  ariaLabel,
  className,
  disabled,
  id,
}: {
  value: string | undefined;
  onValueChange: (value: string) => void;
  options: Option[];
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <RadixSelect.Root
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
    >
      <RadixSelect.Trigger
        id={id}
        aria-label={ariaLabel}
        className={cn(
          "input flex items-center justify-between gap-2 text-left data-[placeholder]:text-ink-faint",
          className,
        )}
      >
        <span className="truncate">
          <RadixSelect.Value placeholder={placeholder} />
        </span>
        <RadixSelect.Icon>
          <ChevronDown className="h-4 w-4 shrink-0 text-ink-faint" />
        </RadixSelect.Icon>
      </RadixSelect.Trigger>
      <RadixSelect.Portal>
        <RadixSelect.Content
          position="popper"
          sideOffset={4}
          className="z-[60] max-h-[min(360px,var(--radix-select-content-available-height))] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-surface-border bg-surface-overlay shadow-overlay animate-scale-in"
        >
          <RadixSelect.Viewport className="p-1">
            {options.map((o) => (
              <RadixSelect.Item
                key={o.value}
                value={o.value}
                disabled={o.disabled}
                className="relative flex cursor-default select-none items-center gap-2 rounded-md py-1.5 pl-2 pr-8 text-sm text-ink outline-none data-[disabled]:opacity-40 data-[highlighted]:bg-surface-hover"
              >
                <div className="min-w-0">
                  <RadixSelect.ItemText>{o.label}</RadixSelect.ItemText>
                  {o.hint && (
                    <div className="truncate text-2xs text-ink-faint">
                      {o.hint}
                    </div>
                  )}
                </div>
                <RadixSelect.ItemIndicator className="absolute right-2">
                  <Check className="h-3.5 w-3.5 text-accent" />
                </RadixSelect.ItemIndicator>
              </RadixSelect.Item>
            ))}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  );
}

// ---------------------------------------------------------------- Switch / Checkbox

export function Switch({
  checked,
  onCheckedChange,
  label,
  disabled,
  id,
}: {
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
  label?: string;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <RadixSwitch.Root
      id={id}
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      aria-label={label}
      className="relative h-5 w-9 shrink-0 rounded-full bg-surface-border transition-colors data-[state=checked]:bg-accent disabled:opacity-50"
    >
      <RadixSwitch.Thumb className="block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px]" />
    </RadixSwitch.Root>
  );
}

export function Checkbox({
  checked,
  onCheckedChange,
  label,
  id,
}: {
  checked: boolean | "indeterminate";
  onCheckedChange: (v: boolean) => void;
  label?: string;
  id?: string;
}) {
  return (
    <RadixCheckbox.Root
      id={id}
      checked={checked}
      onCheckedChange={(v) => onCheckedChange(v === true)}
      aria-label={label}
      className="flex h-4 w-4 shrink-0 items-center justify-center rounded border border-ink-faint/60 bg-surface-sunken data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=indeterminate]:bg-accent"
    >
      <RadixCheckbox.Indicator>
        {checked === "indeterminate" ? (
          <span className="block h-0.5 w-2 bg-white" />
        ) : (
          <Check className="h-3 w-3 text-white" />
        )}
      </RadixCheckbox.Indicator>
    </RadixCheckbox.Root>
  );
}

// ---------------------------------------------------------------- Tabs / segmented

export function Tabs({
  value,
  onValueChange,
  tabs,
  children,
  className,
}: {
  value: string;
  onValueChange: (v: string) => void;
  tabs: { value: string; label: ReactNode; count?: number }[];
  children?: ReactNode;
  className?: string;
}) {
  return (
    <RadixTabs.Root
      value={value}
      onValueChange={onValueChange}
      className={className}
    >
      <RadixTabs.List
        className="flex gap-1 overflow-x-auto border-b border-surface-border"
        aria-label="Sections"
      >
        {tabs.map((t) => (
          <RadixTabs.Trigger
            key={t.value}
            value={t.value}
            className="relative -mb-px flex shrink-0 items-center gap-1.5 border-b-2 border-transparent px-3 py-2 text-sm text-ink-muted transition-colors hover:text-ink data-[state=active]:border-accent data-[state=active]:text-ink"
          >
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className="rounded-full bg-surface-overlay px-1.5 text-2xs tabular-nums text-ink-muted">
                {t.count}
              </span>
            )}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {children}
    </RadixTabs.Root>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
  ariaLabel: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="inline-flex rounded-lg border border-surface-border bg-surface-sunken p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
            value === o.value
              ? "bg-surface-overlay text-ink shadow-sm"
              : "text-ink-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- Date / time

const HOURS = Array.from({ length: 24 }, (_, h) => ({
  value: String(h),
  label: String(h).padStart(2, "0"),
}));
const MINUTES = Array.from({ length: 12 }, (_, i) => ({
  value: String(i * 5),
  label: String(i * 5).padStart(2, "0"),
}));

/** Picks a moment in `timeZone` and returns it as an ISO UTC string. */
export function DateTimePicker({
  value,
  onChange,
  timeZone = "UTC",
  minDate,
  label = "Date and time",
}: {
  value: string | null;
  onChange: (iso: string) => void;
  timeZone?: string;
  minDate?: Date;
  label?: string;
}) {
  const current = useMemo(
    () => new TZDate(value ? new Date(value) : nextRoundedHour(), timeZone),
    [value, timeZone],
  );
  const [month, setMonth] = useState<Date>(() => startOfMonth(current));
  const [open, setOpen] = useState(false);
  const days = useMemo(() => {
    const start = startOfWeek(startOfMonth(month), { weekStartsOn: 1 });
    const end = endOfWeek(endOfMonth(month), { weekStartsOn: 1 });
    const out: Date[] = [];
    for (let d = start; d <= end; d = addDays(d, 1)) out.push(d);
    return out;
  }, [month]);

  const emit = (y: number, m: number, d: number, h: number, min: number) =>
    onChange(new TZDate(y, m, d, h, min, timeZone).toISOString());

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      className="w-[296px]"
      trigger={
        <button
          type="button"
          aria-label={label}
          className="input flex items-center gap-2 text-left"
        >
          <CalendarIcon className="h-4 w-4 text-ink-faint" aria-hidden />
          <span className={value ? "text-ink" : "text-ink-faint"}>
            {value
              ? format(current, "EEE d MMM yyyy, HH:mm")
              : "Pick date and time"}
          </span>
          <span className="ml-auto text-2xs text-ink-faint">{timeZone}</span>
        </button>
      }
    >
      <div className="mb-2 flex items-center justify-between">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Previous month"
          onClick={() => setMonth(addMonths(month, -1))}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="text-sm font-medium">
          {format(month, "LLLL yyyy")}
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Next month"
          onClick={() => setMonth(addMonths(month, 1))}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
      <div className="grid grid-cols-7 gap-0.5 text-center text-2xs text-ink-faint">
        {["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map((d) => (
          <div key={d} className="py-1">
            {d}
          </div>
        ))}
      </div>
      <div
        className="grid grid-cols-7 gap-0.5"
        role="grid"
        aria-label="Calendar"
      >
        {days.map((d) => {
          const disabled = !!minDate && d < startOfDay(minDate);
          const selected = isSameDay(d, current);
          return (
            <button
              key={d.toISOString()}
              type="button"
              disabled={disabled}
              aria-pressed={selected}
              aria-label={format(d, "d MMMM yyyy")}
              onClick={() =>
                emit(
                  d.getFullYear(),
                  d.getMonth(),
                  d.getDate(),
                  current.getHours(),
                  current.getMinutes(),
                )
              }
              className={cn(
                "h-8 rounded-md text-xs tabular-nums transition-colors disabled:opacity-25",
                selected
                  ? "bg-accent text-white"
                  : isSameMonth(d, month)
                    ? "text-ink hover:bg-surface-hover"
                    : "text-ink-faint hover:bg-surface-hover",
              )}
            >
              {d.getDate()}
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Select
          ariaLabel="Hour"
          value={String(current.getHours())}
          options={HOURS}
          className="w-20"
          onValueChange={(h) =>
            emit(
              current.getFullYear(),
              current.getMonth(),
              current.getDate(),
              Number(h),
              current.getMinutes(),
            )
          }
        />
        <span className="text-ink-faint">:</span>
        <Select
          ariaLabel="Minute"
          value={String(current.getMinutes() - (current.getMinutes() % 5))}
          options={MINUTES}
          className="w-20"
          onValueChange={(m) =>
            emit(
              current.getFullYear(),
              current.getMonth(),
              current.getDate(),
              current.getHours(),
              Number(m),
            )
          }
        />
        <Button
          size="sm"
          variant="primary"
          className="ml-auto"
          onClick={() => setOpen(false)}
        >
          Done
        </Button>
      </div>
    </Popover>
  );
}

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function nextRoundedHour() {
  const d = new Date();
  d.setMinutes(0, 0, 0);
  d.setHours(d.getHours() + 1);
  return d;
}

// ---------------------------------------------------------------- Tag input

export function TagInput({
  value,
  onChange,
  placeholder = "Type and press Enter",
  ariaLabel,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  ariaLabel: string;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const parts = draft
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (parts.length)
      onChange([...value, ...parts.filter((p) => !value.includes(p))]);
    setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add();
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1 rounded-lg border border-surface-border bg-surface-sunken px-2 py-1 focus-within:border-accent">
      {value.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-md bg-surface-overlay px-1.5 py-0.5 text-xs text-ink"
        >
          {tag}
          <button
            type="button"
            aria-label={`Remove ${tag}`}
            onClick={() => onChange(value.filter((t) => t !== tag))}
            className="text-ink-faint hover:text-ink"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        aria-label={ariaLabel}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        onBlur={add}
        placeholder={value.length ? "" : placeholder}
        className="min-w-[120px] flex-1 bg-transparent py-0.5 text-sm text-ink outline-none placeholder:text-ink-faint"
      />
    </div>
  );
}
