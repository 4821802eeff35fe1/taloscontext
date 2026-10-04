import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
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
export function JobSummary({ job }: { job: Job }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap justify-between gap-2">
        <span>{job.payload_summary || job.job_type}</span>
        <StatusBadge status={job.status} />
      </div>
      <p className="text-xs text-ink-muted">
        {job.job_type} · Attempt {job.attempt} / {job.max_attempts} ·{" "}
        {duration(job.duration_ms)}
      </p>
      <progress
        className="w-full h-1 accent-accent"
        value={job.progress}
        max={100}
        aria-label="Job progress"
      />
      {job.error_message && (
        <p className="text-xs text-danger">
          {job.error_code}: {job.error_message}
        </p>
      )}
    </div>
  );
}
export function JobsPage({ workspaceId: ws }: { workspaceId: string }) {
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
        title="Jobs"
        description="Persistent background operations and every delivery attempt."
      />
      <div className="flex flex-wrap gap-2">
        <Input
          className="max-w-xs"
          placeholder="Search jobs…"
          aria-label="Search jobs"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select
          className="w-44"
          ariaLabel="Job status"
          value={status}
          onValueChange={setStatus}
          options={[
            "all",
            "QUEUED",
            "RUNNING",
            "RETRYING",
            "SUCCESS",
            "FAILED",
            "CANCELLED",
          ].map((value) => ({
            value,
            label: value === "all" ? "All statuses" : value,
          }))}
        />
        <Select
          className="w-64"
          ariaLabel="Job type"
          value={type}
          onValueChange={setType}
          options={[
            "all",
            "AI_GENERATE_POST",
            "AI_REWRITE",
            "AI_GENERATE_IMAGE",
            "TELEGRAM_PUBLISH",
            "TELEGRAM_RETRY",
            "TELEGRAM_REFRESH_CHANNELS",
            "TELEGRAM_REFRESH_METRICS",
            "AUTOPILOT_PLAN",
            "SOURCE_FETCH",
          ].map((value) => ({
            value,
            label:
              value === "all" ? "All operations" : value.replaceAll("_", " "),
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
            title="No matching jobs"
            description="Generate or publish a post to see operations here."
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
            Load more
          </Button>
        )}
      </Card>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
        title="Job details"
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
                Queued {dateTime(detail.data.queued_at)} · Started{" "}
                {dateTime(detail.data.started_at)} · Worker{" "}
                {detail.data.worker || "—"} · Retry{" "}
                {dateTime(detail.data.next_retry_at)}
              </p>
              <div className="flex gap-2">
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
                    Retry failed
                  </Button>
                )}
                {["QUEUED", "RETRYING"].includes(detail.data.status) && (
                  <Button variant="danger" onClick={() => setCancel(true)}>
                    Cancel queued
                  </Button>
                )}
              </div>
              <pre className="overflow-auto text-xs">
                {JSON.stringify(detail.data.metadata, null, 2)}
              </pre>
              <h3>Attempts</h3>
              {detail.data.attempts.map((a, i) => (
                <div key={i} className="border-t py-2 text-xs">
                  #{a.attempt_number} · {a.status} · {duration(a.duration_ms)} ·{" "}
                  {a.error}
                </div>
              ))}
            </div>
          )
        )}
      </Dialog>
      <ConfirmDialog
        open={cancel}
        onOpenChange={setCancel}
        title="Cancel this job?"
        destructive
        onConfirm={() => {
          action.mutate(() => endpoints.cancelJob(ws, selected!));
          setCancel(false);
        }}
      />
    </div>
  );
}
