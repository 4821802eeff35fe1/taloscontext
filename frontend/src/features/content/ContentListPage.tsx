import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { Card, EmptyState } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Plus } from "@/components/ui/icons";
import { GeneratePostDialog } from "./GeneratePostDialog";
import { ContentDetailPanel } from "./ContentDetailPanel";
import clsx from "clsx";

export function ContentListPage({ workspaceId, statusFilter, title }: { workspaceId: string; statusFilter?: string; title: string }) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const content = useQuery({
    queryKey: ["content", workspaceId, statusFilter],
    queryFn: () => endpoints.content(workspaceId, statusFilter),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">{title}</h1>
        {!statusFilter && (
          <button className="btn-primary" onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" /> Generate with AI
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_1fr]">
        <Card className="max-h-[70vh] overflow-y-auto p-0">
          {content.data && content.data.length > 0 ? (
            <div className="divide-y divide-surface-border">
              {content.data.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setSelectedId(item.id)}
                  className={clsx(
                    "block w-full px-4 py-3 text-left transition-colors hover:bg-surface-overlay",
                    selectedId === item.id && "bg-surface-overlay",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm text-ink">{item.title || item.topic || "Untitled"}</p>
                    <StatusBadge status={item.status} />
                  </div>
                  <p className="mt-0.5 truncate text-xs text-ink-faint">{item.plain_text}</p>
                </button>
              ))}
            </div>
          ) : (
            <div className="p-4">
              <EmptyState title="Nothing here yet" />
            </div>
          )}
        </Card>

        <div>
          {selectedId ? (
            <ContentDetailPanel workspaceId={workspaceId} contentId={selectedId} />
          ) : (
            <Card>
              <EmptyState title="Select a post" description="Choose a post from the list to preview and edit it." />
            </Card>
          )}
        </div>
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
