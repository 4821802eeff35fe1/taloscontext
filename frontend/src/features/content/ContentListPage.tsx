import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  SkeletonRows,
} from "@/components/ui/primitives";
import { Select } from "@/components/ui/forms";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useOperation } from "@/hooks/useOperations";
import { rub } from "@/lib/format";
import { GeneratePostDialog } from "./GeneratePostDialog";
import { ContentDetailPanel } from "./ContentDetailPanel";
export function ContentListPage({
  workspaceId,
  statusFilter,
  title,
}: {
  workspaceId: string;
  statusFilter?: string;
  title: string;
}) {
  const [dialogOpen, setDialogOpen] = useState(
      new URLSearchParams(window.location.search).has("generate"),
    ),
    [q, setQ] = useState(""),
    [status, setStatus] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("post"),
  );
  const filter = statusFilter || (status === "all" ? undefined : status);
  const content = useInfiniteQuery({
    queryKey: ["content", workspaceId, filter, q],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      endpoints.content(workspaceId, {
        status: filter ? [filter] : undefined,
        q,
        cursor: pageParam,
      }),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  const create = useOperation(
    workspaceId,
    async () => {
      const item = await endpoints.createContent(workspaceId, {
        title: "Untitled",
        telegram_html: "",
      });
      setSelectedId(item.id);
    },
    "Draft created",
  );
  const createdFromCommand = useRef(false);
  useEffect(() => {
    if (
      !createdFromCommand.current &&
      new URLSearchParams(window.location.search).has("create")
    ) {
      createdFromCommand.current = true;
      create.mutate();
    }
  }, []);
  const items = content.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="space-y-4">
      <PageHeader
        title={title}
        description="One post. Every channel. One generation cost."
        actions={
          <>
            <Button onClick={() => create.mutate()} loading={create.isPending}>
              Create post
            </Button>
            <Button variant="primary" onClick={() => setDialogOpen(true)}>
              Generate with AI
            </Button>
          </>
        }
      />
      <div className="flex flex-wrap gap-2">
        <Input
          aria-label="Search posts"
          placeholder="Search posts…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="max-w-xs"
        />
        {!statusFilter && (
          <Select
            ariaLabel="Post status"
            value={status}
            onValueChange={setStatus}
            className="w-44"
            options={[
              "all",
              "DRAFT",
              "GENERATING",
              "PENDING_APPROVAL",
              "APPROVED",
              "SCHEDULED",
              "PUBLISHED",
              "FAILED",
              "ARCHIVED",
            ].map((value) => ({
              value,
              label:
                value === "all" ? "All statuses" : value.replaceAll("_", " "),
            }))}
          />
        )}
      </div>
      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="max-h-[70vh] overflow-y-auto">
          {content.isPending ? (
            <SkeletonRows />
          ) : content.isError ? (
            <ErrorState
              error={content.error}
              onRetry={() => void content.refetch()}
            />
          ) : !items.length ? (
            <EmptyState
              title="No posts found"
              description="Create a draft or generate your first post."
            />
          ) : (
            items.map((item) => (
              <button
                key={item.id}
                onClick={() => setSelectedId(item.id)}
                className={`block w-full border-b p-4 text-left hover:bg-surface-overlay ${selectedId === item.id ? "bg-surface-overlay" : ""}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">
                    {item.title || item.topic || "Untitled"}
                  </span>
                  <StatusBadge status={item.status} />
                </div>
                <p className="my-2 line-clamp-2 text-xs text-ink-muted">
                  {item.excerpt}
                </p>
                <div className="flex justify-between text-xs text-ink-faint">
                  <span>{item.channel_set_name || "No target"}</span>
                  <span>AI {rub(item.ai_cost_rub)}</span>
                </div>
              </button>
            ))
          )}
          {content.hasNextPage && (
            <Button
              className="m-3"
              onClick={() => void content.fetchNextPage()}
              loading={content.isFetchingNextPage}
            >
              Load more
            </Button>
          )}
        </Card>
        {selectedId ? (
          <ContentDetailPanel
            key={workspaceId + selectedId}
            workspaceId={workspaceId}
            contentId={selectedId}
          />
        ) : (
          <Card>
            <EmptyState
              title="Select a post"
              description="Edit, preview, approve and schedule from here."
            />
          </Card>
        )}
      </div>
      <GeneratePostDialog
        workspaceId={workspaceId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={setSelectedId}
      />
    </div>
  );
}
