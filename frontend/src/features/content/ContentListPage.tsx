import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { statusLabel } from "@/i18n/labels";
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
  titleKey,
}: {
  workspaceId: string;
  statusFilter?: string;
  titleKey: "posts" | "approval";
}) {
  const { t } = useTranslation("content");
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
        title: "",
        telegram_html: "",
      });
      setSelectedId(item.id);
    },
    t("list.draftCreated"),
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
        title={t(`list.title.${titleKey}`)}
        description={t("list.description")}
        actions={
          <>
            <Button onClick={() => create.mutate()} loading={create.isPending}>
              {t("list.createPost")}
            </Button>
            <Button variant="primary" onClick={() => setDialogOpen(true)}>
              {t("list.generateWithAi")}
            </Button>
          </>
        }
      />
      <div className="flex flex-wrap gap-2">
        <Input
          aria-label={t("list.search")}
          placeholder={t("list.searchPlaceholder")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="max-w-xs"
        />
        {!statusFilter && (
          <Select
            ariaLabel={t("list.statusFilter")}
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
              label: value === "all" ? t("list.allStatuses") : statusLabel(value, "content"),
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
              title={t("list.empty.title")}
              description={t("list.empty.description")}
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
                    {item.title || item.topic || t("common:untitled")}
                  </span>
                  <StatusBadge status={item.status} domain="content" />
                </div>
                <p className="my-2 line-clamp-2 text-xs text-ink-muted">
                  {item.excerpt}
                </p>
                <div className="flex justify-between text-xs text-ink-faint">
                  <span className="truncate">{item.channel_set_name || t("list.noTarget")}</span>
                  <span className="shrink-0">{t("list.aiCost", { cost: rub(item.ai_cost_rub) })}</span>
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
              {t("common:action.loadMore")}
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
              title={t("list.select.title")}
              description={t("list.select.description")}
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
