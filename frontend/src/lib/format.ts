/**
 * Locale-aware presentation helpers. They read the active UI language at call
 * time, so components re-render with new formats after a language switch.
 * Values from the API (UTC datetimes, Decimal strings) are never changed —
 * this is presentation only.
 */
import { TZDate } from "@date-fns/tz";
import { intlLocale } from "@/i18n/language";

const DASH = "—";

function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "string" ? Number(value) : value;
  return Number.isFinite(n) ? n : null;
}

/** 1 250 430 (ru) / 1,250,430 (en) */
export function number(value: string | number | null | undefined, maxDigits = 0): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  return new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: maxDigits }).format(n);
}

/** 1 249,52 ₽ (ru) / RUB 1,249.52 (en) */
export function rub(value: string | number | null | undefined, digits = 2): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const locale = intlLocale();
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "RUB",
    currencyDisplay: locale.startsWith("ru") ? "symbol" : "code",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  return new Intl.NumberFormat(intlLocale(), { style: "percent", maximumFractionDigits: digits }).format(value);
}

export function compact(n: number | null | undefined): string {
  if (n === null || n === undefined) return DASH;
  return new Intl.NumberFormat(intlLocale(), { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

function unit(value: number, unitName: string, digits = 0): string {
  return new Intl.NumberFormat(intlLocale(), {
    style: "unit", unit: unitName, unitDisplay: "short", maximumFractionDigits: digits,
  }).format(value);
}

export function bytes(n: number): string {
  if (n < 1024) return unit(n, "byte");
  if (n < 1024 * 1024) return unit(Math.round(n / 1024), "kilobyte");
  return unit(n / 1024 / 1024, "megabyte", 1);
}

export function inTz(iso: string, tz: string): TZDate {
  return new TZDate(new Date(iso), tz);
}

export type DateStyle = "datetime" | "date" | "time" | "full" | "weekday-date" | "month-year";

/**
 * Formats a UTC ISO timestamp in a timezone.
 *   en: Oct 5, 11:42 PM   ·  ru: 5 окт., 23:42
 * The year is added when it isn't the current one ("full" always shows it).
 * Legacy date-fns patterns are mapped: "HH:mm" -> time, anything else -> datetime.
 */
export function dateTime(iso: string | null | undefined, tz = "UTC", style: DateStyle | string = "datetime"): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return DASH;
  const kind: DateStyle = (["datetime", "date", "time", "full", "weekday-date", "month-year"] as string[]).includes(style)
    ? (style as DateStyle)
    : style === "HH:mm" ? "time" : "datetime";
  const showYear = kind === "full" || new Date().getFullYear() !== yearIn(d, tz);
  const opts: Intl.DateTimeFormatOptions = { timeZone: tz };
  if (kind === "time") Object.assign(opts, { hour: "numeric", minute: "2-digit" });
  else if (kind === "month-year") Object.assign(opts, { month: "long", year: "numeric" });
  else {
    Object.assign(opts, { month: "short", day: "numeric", ...(showYear ? { year: "numeric" } : {}) });
    if (kind === "weekday-date") opts.weekday = "short";
    if (kind === "datetime" || kind === "full") Object.assign(opts, { hour: "numeric", minute: "2-digit" });
  }
  return new Intl.DateTimeFormat(intlLocale(), opts).format(d);
}

function yearIn(d: Date, tz: string): number {
  return Number(new Intl.DateTimeFormat("en-US", { timeZone: tz, year: "numeric" }).format(d));
}

/** Plain calendar date (no timezone shift), e.g. a day cell or "2026-03-10". */
export function calendarDate(d: Date, style: "day" | "weekday-day" | "long" | "month-year" = "long"): string {
  const opts: Intl.DateTimeFormatOptions =
    style === "day" ? { day: "numeric" }
      : style === "weekday-day" ? { weekday: "short", day: "numeric" }
        : style === "month-year" ? { month: "long", year: "numeric" }
          : { day: "numeric", month: "long", year: "numeric" };
  return new Intl.DateTimeFormat(intlLocale(), opts).format(d);
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 86400], ["month", 30 * 86400], ["day", 86400], ["hour", 3600], ["minute", 60], ["second", 1],
];

/** "5 minutes ago" / "через 2 часа" */
export function relative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return DASH;
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat(intlLocale(), { numeric: "auto" });
  for (const [u, size] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= size || u === "second") return rtf.format(Math.round(seconds / size), u);
  }
  return DASH;
}

export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return DASH;
  if (ms < 1000) return unit(ms, "millisecond");
  if (ms < 60_000) return unit(ms / 1000, "second", 1);
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${unit(minutes, "minute")} ${unit(seconds, "second")}`;
}

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export const COMMON_TIMEZONES = [
  "UTC", "Europe/Moscow", "Europe/Kaliningrad", "Europe/Samara", "Asia/Yekaterinburg", "Asia/Omsk",
  "Asia/Novosibirsk", "Asia/Krasnoyarsk", "Asia/Irkutsk", "Asia/Vladivostok", "Europe/Berlin", "Europe/London",
  "Europe/Kyiv", "Asia/Almaty", "Asia/Tashkent", "Asia/Dubai", "Asia/Tbilisi", "America/New_York",
];

export function timezoneOptions(extra?: string) {
  const list = extra && !COMMON_TIMEZONES.includes(extra) ? [extra, ...COMMON_TIMEZONES] : COMMON_TIMEZONES;
  return list.map((tz) => ({ value: tz, label: tz.replace("_", " ") }));
}
