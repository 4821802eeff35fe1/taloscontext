import { describe, expect, it, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { BudgetBar } from "@/features/analytics/CostDashboardPage";
import { SetHealth } from "@/features/channels/ChannelSetsPage";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { JobSummary } from "@/features/jobs/JobsPage";
import { TRANSFORM_ACTIONS } from "@/features/content/ContentDetailPanel";
import { calendarDays, moveToDay } from "@/lib/calendar";
import { eventQueryPrefixes } from "@/hooks/useRealtime";
import { qs, api, ApiError, type ChannelSet, type Job } from "@/lib/api";
import { TZDate } from "@date-fns/tz";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("budget", () => {
  it("caps the progress at 100 with over-budget warning", () => {
    render(<BudgetBar spent="120" budget="100" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
    expect(screen.getByText("120%")).toBeInTheDocument();
  });
  it("handles zero budgets without NaN", () => {
    render(<BudgetBar spent="0" budget="0" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
  });
  it("uses the configured warning threshold", () => {
    const { container } = render(
      <BudgetBar spent="60" budget="100" warning={50} />,
    );
    expect(container.querySelector(".bg-warning")).not.toBeNull();
  });
});
it("publication partial status is explicit", () => {
  render(<StatusBadge status="PARTIALLY_PUBLISHED" />);
  expect(screen.getByText("Partly published")).toBeInTheDocument();
});
it("unknown delivery is visible", () => {
  render(<StatusBadge status="DELIVERY_UNKNOWN" />);
  expect(screen.getByText("Delivery unknown")).toBeInTheDocument();
});
it("channel set reports unhealthy members", () => {
  render(
    <SetHealth set={{ healthy_count: 3, member_count: 5 } as ChannelSet} />,
  );
  expect(screen.getByText("3 / 5 ready")).toHaveClass("text-warning");
});
it("jobs show real attempts and failure", () => {
  render(
    <JobSummary
      job={
        {
          status: "FAILED",
          payload_summary: "Publish post",
          job_type: "TELEGRAM_PUBLISH",
          attempt: 2,
          max_attempts: 5,
          progress: 40,
          error_code: "FLOOD_WAIT",
          error_message: "Wait 60 seconds",
          duration_ms: 1000,
        } as Job
      }
    />,
  );
  expect(screen.getByText(/Attempt 2 \/ 5/)).toBeInTheDocument();
  expect(screen.getByText("FLOOD_WAIT: Wait 60 seconds")).toBeInTheDocument();
});
it("all required editor actions use unique operation keys", () => {
  expect(TRANSFORM_ACTIONS).toHaveLength(9);
  expect(new Set(TRANSFORM_ACTIONS.map(([op]) => op)).size).toBe(9);
  expect(TRANSFORM_ACTIONS.map(([op]) => op)).toContain("regenerate_fragment");
});
describe("calendar timezone and DST", () => {
  it("month cells are full Monday weeks", () => {
    const days = calendarDays(
      new Date("2026-10-15T12:00:00Z"),
      "month",
      "Europe/Moscow",
    );
    expect(days.length % 7).toBe(0);
    expect(days[0].getDay()).toBe(1);
  });
  it("day boundaries use the selected timezone", () => {
    const days = calendarDays(
      new Date("2026-10-05T22:00:00Z"),
      "day",
      "Europe/Moscow",
    );
    expect(new Date(days[0]).toISOString()).toBe("2026-10-05T21:00:00.000Z");
  });
  it("moving across DST keeps the local hour", () => {
    const result = moveToDay(
      "2026-03-28T10:00:00Z",
      new TZDate(2026, 2, 29, "Europe/Berlin"),
      "Europe/Berlin",
    );
    expect(new Date(result).toISOString()).toBe("2026-03-29T09:00:00.000Z");
  });
  it("week spans seven days even over DST", () => {
    expect(
      calendarDays(new Date("2026-03-29T12:00:00Z"), "week", "Europe/Berlin"),
    ).toHaveLength(7);
  });
});
it("realtime invalidates affected queries", () => {
  expect(eventQueryPrefixes("publication.published")).toContain("batches");
  expect(eventQueryPrefixes("content.updated")).toContain("revisions");
});
it("query arrays use repeated keys", () => {
  expect(qs({ status: ["DRAFT", "FAILED"], q: "a & b", empty: null })).toBe(
    "?status=DRAFT&status=FAILED&q=a+%26+b",
  );
});
it("API sends credential cookies and CSRF header", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response("{}", { status: 200 }));
  await api.post("/test", { x: 1 });
  expect(fetch.mock.calls[0][1]).toMatchObject({
    credentials: "include",
    headers: {
      "X-ChannelOS-Client": "web",
      "Content-Type": "application/json",
    },
  });
});
it("rate limiting exposes Retry-After", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ detail: "Try later" }), {
      status: 429,
      headers: { "Retry-After": "60" },
    }),
  );
  try {
    await api.post("/test");
    throw new Error("expected rejection");
  } catch (e) {
    expect(e).toBeInstanceOf(ApiError);
    expect((e as ApiError).retryAfter).toBe(60);
  }
});
