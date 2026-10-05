/**
 * Central translations for machine-readable values coming from the API.
 * Backend enums stay as-is (PENDING_APPROVAL, FLOOD_WAIT, content.created…);
 * only their presentation is localized here — never with ad-hoc switches in
 * components.
 *
 * Unknown values fall back to a humanized version of the raw value, so a new
 * backend enum never renders as an empty string.
 */
import i18n from "./index";

export type StatusDomain =
  | "content" | "publication" | "batch" | "job" | "account" | "channel" | "series" | "idea"
  | "source" | "flow" | "media" | "provider" | "schedule";

function humanize(value: string): string {
  const s = value.replace(/[._]/g, " ").toLowerCase().trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function lookup(keys: string[], value: string, options?: Record<string, unknown>): string {
  for (const key of keys) {
    if (i18n.exists(key)) return i18n.t(key, options) as string;
  }
  return humanize(value);
}

/** Status label; a domain may refine the generic wording. */
export function statusLabel(status: string, domain?: StatusDomain): string {
  if (!status) return "";
  const keys = domain ? [`common:status.${domain}.${status}`, `common:status.any.${status}`] : [`common:status.any.${status}`];
  return lookup(keys, status);
}

export function jobTypeLabel(type: string) {
  return lookup([`automation:jobType.${type}`], type);
}

export function aiOperationLabel(op: string) {
  return lookup([`content:operation.${op}`, `content:operation.${op.toLowerCase()}`], op);
}

export function auditActionLabel(action: string) {
  return lookup([`system:audit.action.${action.replaceAll(".", "_")}`], action);
}

export function entityLabel(entity: string) {
  return lookup([`system:audit.entity.${entity}`], entity);
}

export function knowledgeKindLabel(kind: string) {
  return lookup([`ai:knowledge.kind.${kind}`], kind);
}

export function sourceKindLabel(kind: string) {
  return lookup([`ai:sources.kind.${kind}`], kind);
}

export function roleLabel(role: string) {
  return lookup([`settings:role.${role}`], role);
}

export function channelSetModeLabel(mode: string) {
  return lookup([`channels:mode.${mode}.label`], mode);
}

export function misfirePolicyLabel(policy: string) {
  return lookup([`automation:misfire.${policy}.label`], policy);
}

export function autopilotModeLabel(mode: string) {
  return lookup([`automation:autopilot.mode.${mode}.label`], mode);
}

export function ctaKeyLabel(key: string) {
  return lookup([`common:cta.${key}`], key);
}

export function categoryLabel(category: string) {
  if (!category) return "";
  return lookup([`common:category.${category}`], category);
}

export function periodLabel(period: string) {
  return lookup([`common:period.${period}`], period);
}

export type NotificationLike = { kind: string; message: string; metadata: Record<string, unknown> };

/**
 * Renders a notification in the viewer's language from kind + metadata. The
 * stored English message is only used when the parameters a translation needs
 * are missing (notifications created before v0.3).
 */
export function notificationText(n: NotificationLike): string {
  const key = `system:notification.${n.kind.replaceAll(".", "_")}`;
  if (!i18n.exists(key)) return n.message;
  const m = n.metadata ?? {};
  const required: Record<string, string[]> = {
    "post.published": ["title", "published", "total"],
    "post.partially_published": ["title", "published", "total", "failed"],
    "post.failed": ["title", "total"],
    "telegram.flood_wait": ["phone", "retry_at"],
    "telegram.disconnected": ["phone"],
    "budget.warning": ["period", "spent", "limit"],
    "budget.exceeded": ["period", "spent", "limit"],
    "approval.required": ["title"],
    "schedule.misfired": ["count"],
  };
  const missing = (required[n.kind] ?? []).some((k) => m[k] === undefined || m[k] === null);
  if (missing) return n.message;
  return i18n.t(key, {
    ...m,
    title: (m.title as string) || i18n.t("common:untitled"),
    period: m.period ? periodLabel(String(m.period)) : "",
    count: typeof m.count === "number" ? m.count : Number(m.total ?? 0),
    retry_time: m.retry_at
      ? new Intl.DateTimeFormat(i18n.language === "ru" ? "ru-RU" : "en-US", { hour: "numeric", minute: "2-digit" }).format(new Date(String(m.retry_at)))
      : "",
    spent_fmt: m.spent !== undefined ? formatRub(String(m.spent)) : "",
    limit_fmt: m.limit !== undefined ? formatRub(String(m.limit)) : "",
    error: m.error_code ? errorLabel(String(m.error_code)) : "",
  });
}

function formatRub(v: string) {
  const ru = i18n.language === "ru";
  return new Intl.NumberFormat(ru ? "ru-RU" : "en-US", {
    style: "currency", currency: "RUB", currencyDisplay: ru ? "symbol" : "code",
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(Number(v));
}

/** Localized text for an API/job/publication error code; null if unknown. */
export function errorLabel(code: string, params: Record<string, unknown> = {}): string {
  const key = `errors:${code}`;
  return i18n.exists(key) ? (i18n.t(key, params) as string) : humanize(code);
}

export function knownError(code: string | null | undefined): boolean {
  return !!code && i18n.exists(`errors:${code}`);
}
