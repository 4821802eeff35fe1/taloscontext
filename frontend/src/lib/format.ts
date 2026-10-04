import { TZDate } from "@date-fns/tz";
import { format, formatDistanceToNowStrict } from "date-fns";

export function rub(
  value: string | number | null | undefined,
  digits = 2,
): string {
  const n = typeof value === "string" ? Number(value) : (value ?? 0);
  if (!Number.isFinite(n)) return "—";
  return `${n.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits })} ₽`;
}

export function compact(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function inTz(iso: string, tz: string): TZDate {
  return new TZDate(new Date(iso), tz);
}

export function dateTime(
  iso: string | null | undefined,
  tz = "UTC",
  pattern = "d MMM, HH:mm",
): string {
  if (!iso) return "—";
  return format(inTz(iso, tz), pattern);
}

export function relative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const past = d.getTime() < Date.now();
  const text = formatDistanceToNowStrict(d);
  return past ? `${text} ago` : `in ${text}`;
}

export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export const COMMON_TIMEZONES = [
  "UTC",
  "Europe/Moscow",
  "Europe/Kaliningrad",
  "Europe/Samara",
  "Asia/Yekaterinburg",
  "Asia/Omsk",
  "Asia/Novosibirsk",
  "Asia/Krasnoyarsk",
  "Asia/Irkutsk",
  "Asia/Vladivostok",
  "Europe/Berlin",
  "Europe/London",
  "Europe/Kyiv",
  "Asia/Almaty",
  "Asia/Tashkent",
  "Asia/Dubai",
  "Asia/Tbilisi",
  "America/New_York",
];

export function timezoneOptions(extra?: string) {
  const list =
    extra && !COMMON_TIMEZONES.includes(extra)
      ? [extra, ...COMMON_TIMEZONES]
      : COMMON_TIMEZONES;
  return list.map((tz) => ({ value: tz, label: tz.replace("_", " ") }));
}
