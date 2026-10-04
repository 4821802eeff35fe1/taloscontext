import { TZDate } from "@date-fns/tz";
import {
  addDays,
  endOfMonth,
  endOfWeek,
  startOfDay,
  startOfMonth,
  startOfWeek,
} from "date-fns";
export type CalendarMode = "month" | "week" | "day";
export function calendarDays(
  anchor: Date,
  mode: CalendarMode,
  tz: string,
): Date[] {
  const local = new TZDate(anchor, tz);
  const start =
    mode === "month"
      ? startOfWeek(startOfMonth(local), { weekStartsOn: 1 })
      : mode === "week"
        ? startOfWeek(local, { weekStartsOn: 1 })
        : startOfDay(local);
  const end =
    mode === "month"
      ? endOfWeek(endOfMonth(local), { weekStartsOn: 1 })
      : mode === "week"
        ? endOfWeek(local, { weekStartsOn: 1 })
        : start;
  const days: Date[] = [];
  for (let d = start; d <= end; d = addDays(d, 1)) days.push(d);
  return days;
}
export function moveToDay(at: string, day: Date, tz: string): string {
  const original = new TZDate(new Date(at), tz);
  return new TZDate(
    day.getFullYear(),
    day.getMonth(),
    day.getDate(),
    original.getHours(),
    original.getMinutes(),
    tz,
  ).toISOString();
}
