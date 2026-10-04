import clsx from "clsx";

const TONE: Record<string, string> = {
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  danger: "bg-danger/15 text-danger",
  neutral: "bg-surface-overlay text-ink-muted",
  accent: "bg-accent/15 text-accent",
};

const STATUS_TONE: Record<string, keyof typeof TONE> = {
  CONNECTED: "success",
  HEALTHY: "success",
  SUCCESS: "success",
  PUBLISHED: "success",
  APPROVED: "success",
  AVAILABLE: "success",

  DRAFT: "neutral",
  IDEA: "neutral",
  PENDING: "neutral",
  QUEUED: "neutral",
  UNAVAILABLE: "neutral",
  DISCONNECTED: "neutral",

  PENDING_APPROVAL: "warning",
  GENERATING: "warning",
  SCHEDULED: "warning",
  RETRYING: "warning",
  FLOOD_WAIT: "warning",
  PARTIAL_FAILURE: "warning",
  PARTIALLY_PUBLISHED: "warning",
  AUTH_REQUIRED: "warning",
  TWO_FA_REQUIRED: "warning",

  FAILED: "danger",
  REJECTED: "danger",
  ERROR: "danger",
  CANCELLED: "danger",
  NO_PERMISSION: "danger",

  PUBLISHING: "accent",
  RUNNING: "accent",
  CLAIMED: "accent",
  SENDING: "accent",
};

export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  return (
    <span className={clsx("badge", TONE[tone])}>
      {status.replaceAll("_", " ").toLowerCase()}
    </span>
  );
}
