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

/** True for plain keys and for keys that only exist in plural forms. */
function hasKey(key: string): boolean {
  return i18n.exists(key) || i18n.exists(key, { count: 1 });
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
  // Parameterized actions: content.ai_<operation>, content.misfire_<policy>, publication.marked_<outcome>
  const ai = /^content\.ai_(.+)$/.exec(action);
  if (ai) return i18n.t("system:audit.actionName.content_ai", { operation: aiOperationLabel(ai[1].toUpperCase()) }) as string;
  const misfire = /^content\.misfire_(.+)$/.exec(action);
  if (misfire) return i18n.t("system:audit.actionName.content_misfire", { policy: misfirePolicyLabel(misfire[1].toUpperCase()) }) as string;
  return lookup([`system:audit.actionName.${action.replaceAll(".", "_")}`], action);
}

export function entityLabel(entity: string) {
  return lookup([`system:audit.entityName.${entity}`], entity);
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
  return lookup([`automation:autopilot.modeName.${mode}.label`], mode);
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
  if (!hasKey(key)) return n.message;
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
  return hasKey(key) ? (i18n.t(key, params) as string) : humanize(code);
}

export function knownError(code: string | null | undefined): boolean {
  return !!code && hasKey(`errors:${code}`);
}

// Import warnings are stored as English sentences; known shapes are mapped
// to translated templates, anything else is shown verbatim.
const KNOWLEDGE_WARNINGS: [RegExp, string][] = [
  [/^Skipped (\d+) service messages$/, "serviceSkipped"],
  [/^Skipped (\d+) posts without text \(media only\)$/, "mediaSkipped"],
  [/^Text truncated to (\d+) characters$/, "truncated"],
  [/^Only the first (\d+) entries were imported$/, "limited"],
];

export function knowledgeWarningLabel(warning: string): string {
  for (const [pattern, key] of KNOWLEDGE_WARNINGS) {
    const match = pattern.exec(warning);
    if (match) return i18n.t(`ai:knowledge.warning.${key}`, { count: Number(match[1]) }) as string;
  }
  return warning;
}

// Job summaries are stored as English text with user content after a fixed
// prefix ("Fetch <source>", "Shorten: <title>"); the prefix is translated and
// the user content is kept as-is.
const JOB_SUMMARIES: [RegExp, string][] = [
  [/^Generate: ([\s\S]*)$/, "generate"],
  [/^Image: ([\s\S]*)$/, "image"],
  [/^Retry publish to ([\s\S]*)$/, "retryPublish"],
  [/^Publish to ([\s\S]*)$/, "publish"],
  [/^Fetch ([\s\S]*)$/, "fetch"],
  [/^Import channels for ([\s\S]*)$/, "importChannels"],
  [/^Autopilot plan for (\d{4}-\d{2}-\d{2})$/, "autopilotPlan"],
  [/^Refresh post metrics \(last 7 days\)$/, "refreshMetrics"],
];

export function jobSummaryLabel(summary: string, jobType: string): string {
  if (!summary) return jobTypeLabel(jobType);
  for (const [pattern, key] of JOB_SUMMARIES) {
    const match = pattern.exec(summary);
    if (match) return i18n.t(`automation:jobSummary.${key}`, { value: match[1] ?? "" }) as string;
  }
  // AI transforms: "<Operation name>: <title>"
  const transform = /^([A-Z][a-z]+(?: [a-z]+)*): ([\s\S]*)$/.exec(summary);
  if (transform) {
    const op = transform[1].toUpperCase().replaceAll(" ", "_");
    if (i18n.exists(`content:operation.${op}`)) return `${aiOperationLabel(op)}: ${transform[2]}`;
  }
  return summary;
}
