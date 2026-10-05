import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, type Job } from "@/lib/api";
import {
  Card,
  Button,
  Input,
  PageHeader,
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "@/components/ui/primitives";
import { Select } from "@/components/ui/forms";
import { Dialog, ConfirmDialog } from "@/components/ui/overlays";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useOperation } from "@/hooks/useOperations";
import { dateTime, duration } from "@/lib/format";
import { errorLabel, jobSummaryLabel, jobTypeLabel, statusLabel } from "@/i18n/labels";

const JOB_STATUSES = ["QUEUED", "RUNNING", "RETRYING", "SUCCESS", "FAILED", "CANCELLED"];
const JOB_TYPES = [
  "AI_GENERATE_POST",
  "AI_REWRITE",
  "AI_GENERATE_IMAGE",
  "TELEGRAM_PUBLISH",
  "TELEGRAM_RETRY",
  "TELEGRAM_REFRESH_CHANNELS",
  "TELEGRAM_REFRESH_METRICS",
  "AUTOPILOT_PLAN",
  "SOURCE_FETCH",
];

export function JobSummary({ job }: { job: Job }) {
  const { t } = useTranslation("automation");
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap justify-between gap-2">
        <span className="min-w-0 break-words">{jobSummaryLabel(job.payload_summary, job.job_type)}</span>
        <StatusBadge status={job.status} domain="job" />
      </div>
      <p className="text-xs text-ink-muted">
        {jobTypeLabel(job.job_type)} ·{" "}
        {t("jobs.attempt", { attempt: job.attempt, max: job.max_attempts })} ·{" "}
        {duration(job.duration_ms)}
      </p>
      <progress
        className="w-full h-1 accent-accent"
        value={job.progress}
        max={100}
        aria-label={t("jobs.progress")}
      />
      {(job.error_code || job.error_message) && (
        <p className="break-words text-xs text-danger" title={job.error_message ?? undefined}>
          {job.error_code ? errorLabel(job.error_code) : job.error_message}
        </p>
      )}
    </div>
  );
}
export function JobsPage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("automation");
  const [q, setQ] = useState(""),
    [status, setStatus] = useState("all"),
    [type, setType] = useState("all"),
    [selected, setSelected] = useState<string | null>(null),
    [cancel, setCancel] = useState(false);
  const jobs = useInfiniteQuery({
    queryKey: ["jobs", ws, q, status, type],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      endpoints.jobs(ws, {
        q,
        status: status === "all" ? undefined : [status],
        type: type === "all" ? undefined : [type],
        cursor: pageParam,
      }),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
    refetchInterval: 15000,
  });
  const detail = useQuery({
    queryKey: ["job", ws, selected],
    queryFn: () => endpoints.job(ws, selected!),
    enabled: !!selected,
    refetchInterval: 5000,
  });
  const action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader
        title={t("jobs.title")}
        description={t("jobs.description")}
      />
      <div className="flex flex-wrap gap-2">
        <Input
          className="w-full sm:max-w-xs"
          placeholder={t("jobs.searchPlaceholder")}
          aria-label={t("jobs.search")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select
          className="w-full sm:w-44"
          ariaLabel={t("jobs.status")}
          value={status}
          onValueChange={setStatus}
          options={["all", ...JOB_STATUSES].map((value) => ({
            value,
            label: value === "all" ? t("jobs.allStatuses") : statusLabel(value, "job"),
          }))}
        />
        <Select
          className="w-full sm:w-64"
          ariaLabel={t("jobs.type")}
          value={type}
          onValueChange={setType}
          options={["all", ...JOB_TYPES].map((value) => ({
            value,
            label: value === "all" ? t("jobs.allTypes") : jobTypeLabel(value),
          }))}
        />
      </div>
      <Card>
        {jobs.isPending ? (
          <SkeletonRows />
        ) : jobs.isError ? (
          <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} />
        ) : !jobs.data.pages[0].items.length ? (
          <EmptyState
            title={t("jobs.empty.title")}
            description={t("jobs.empty.description")}
          />
        ) : (
          jobs.data.pages
            .flatMap((p) => p.items)
            .map((job) => (
              <button
                className="block w-full text-left border-b p-4 hover:bg-surface-overlay"
                key={job.id}
                onClick={() => setSelected(job.id)}
              >
                <JobSummary job={job} />
              </button>
            ))
        )}
        {jobs.hasNextPage && (
          <Button className="m-4" onClick={() => void jobs.fetchNextPage()}>
            {t("common:action.loadMore")}
          </Button>
        )}
      </Card>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
        title={t("jobs.details")}
        size="lg"
      >
        {detail.isPending ? (
          <SkeletonRows />
        ) : detail.isError ? (
          <ErrorState error={detail.error} />
        ) : (
          detail.data && (
            <div className="space-y-4">
              <JobSummary job={detail.data} />
              <p className="text-xs text-ink-muted">
                {[
                  t("jobs.queued", { time: dateTime(detail.data.queued_at) }),
                  detail.data.started_at && t("jobs.started", { time: dateTime(detail.data.started_at) }),
                  detail.data.worker && t("jobs.worker", { worker: detail.data.worker }),
                  detail.data.next_retry_at && t("jobs.nextRetry", { time: dateTime(detail.data.next_retry_at) }),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              {detail.data.error_message && (
                <p className="break-words text-xs text-ink-muted">
                  {t("jobs.technical")}: <span className="font-mono">{detail.data.error_message}</span>
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                {detail.data.status === "FAILED" && (
                  <Button
                    disabled={
                      action.isPending ||
                      detail.data.error_code === "DELIVERY_UNKNOWN"
                    }
                    onClick={() =>
                      action.mutate(() => endpoints.retryJob(ws, selected!))
                    }
                  >
                    {t("jobs.retry")}
                  </Button>
                )}
                {["QUEUED", "RETRYING"].includes(detail.data.status) && (
                  <Button variant="danger" onClick={() => setCancel(true)}>
                    {t("jobs.cancel")}
                  </Button>
                )}
              </div>
              <pre className="overflow-auto text-xs">
                {JSON.stringify(detail.data.metadata, null, 2)}
              </pre>
              <h3>{t("jobs.attempts")}</h3>
              {detail.data.attempts.map((a, i) => (
                <div key={i} className="border-t py-2 text-xs">
                  #{a.attempt_number} · {statusLabel(a.status, "job")} · {duration(a.duration_ms)}
                  {a.error && <span className="break-words font-mono"> · {a.error}</span>}
                </div>
              ))}
            </div>
          )
        )}
      </Dialog>
      <ConfirmDialog
        open={cancel}
        onOpenChange={setCancel}
        title={t("jobs.cancelConfirm")}
        destructive
        onConfirm={() => {
          action.mutate(() => endpoints.cancelJob(ws, selected!));
          setCancel(false);
        }}
      />
    </div>
  );
}
