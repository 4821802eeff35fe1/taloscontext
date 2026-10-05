import { useTranslation } from "react-i18next";
import { statusLabel as translateStatus, type StatusDomain } from "@/i18n/labels";
import { cn } from "./primitives";

type Tone = "success" | "warning" | "danger" | "neutral" | "accent" | "info";

const TONE: Record<Tone, string> = {
  success: "bg-success/12 text-success ring-success/25",
  warning: "bg-warning/12 text-warning ring-warning/25",
  danger: "bg-danger/12 text-danger ring-danger/25",
  neutral: "bg-surface-overlay text-ink-muted ring-surface-border",
  accent: "bg-accent/12 text-accent ring-accent/25",
  info: "bg-info/12 text-info ring-info/25",
};

const STATUS_TONE: Record<string, Tone> = {
  CONNECTED: "success",
  HEALTHY: "success",
  SUCCESS: "success",
  PUBLISHED: "success",
  APPROVED: "success",
  AVAILABLE: "success",
  COMPLETED: "success",
  ACTIVE: "success",
  USED: "success",
  DRAFT: "neutral",
  IDEA: "neutral",
  PENDING: "neutral",
  QUEUED: "neutral",
  UNAVAILABLE: "neutral",
  DISCONNECTED: "neutral",
  ARCHIVED: "neutral",
  CANCELLED: "neutral",
  DISMISSED: "neutral",
  PAUSED: "neutral",
  NEW: "info",
  SHORTLISTED: "accent",
  PENDING_APPROVAL: "warning",
  SCHEDULED: "info",
  RETRYING: "warning",
  FLOOD_WAIT: "warning",
  PARTIAL_FAILURE: "warning",
  PARTIALLY_PUBLISHED: "warning",
  AUTH_REQUIRED: "warning",
  TWO_FA_REQUIRED: "warning",
  CODE_REQUIRED: "info",
  PASSWORD_REQUIRED: "info",
  EXPIRED: "neutral",
  FAILED: "danger",
  REJECTED: "danger",
  ERROR: "danger",
  NO_POST_PERMISSION: "danger",
  NO_PERMISSION: "danger",
  DELIVERY_UNKNOWN: "danger",
  PUBLISHING: "accent",
  RUNNING: "accent",
  CLAIMED: "accent",
  SENDING: "accent",
  GENERATING: "accent",
  AUTHORIZING: "accent",
};

/** @deprecated import statusLabel from "@/i18n/labels" — kept for existing call sites. */
export function statusLabel(status: string, domain?: StatusDomain) {
  return translateStatus(status, domain);
}

export function StatusBadge({
  status,
  domain,
  className,
}: {
  status: string;
  domain?: StatusDomain;
  className?: string;
}) {
  useTranslation(); // re-render on language change
  const tone = STATUS_TONE[status] ?? "neutral";
  const live =
    tone === "accent" &&
    ["RUNNING", "PUBLISHING", "GENERATING", "SENDING"].includes(status);
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-2xs font-medium ring-1 ring-inset",
        TONE[tone],
        className,
      )}
    >
      {live && (
        <span
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-current"
          aria-hidden
        />
      )}
      {translateStatus(status, domain)}
    </span>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-2xs font-medium ring-1 ring-inset",
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
