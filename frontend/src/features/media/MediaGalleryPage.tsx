import { useRef, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { endpoints, mediaUrl } from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SkeletonRows,
  Textarea,
} from "@/components/ui/primitives";
import { Tabs } from "@/components/ui/forms";
import { Dialog, Tooltip } from "@/components/ui/overlays";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useOperation } from "@/hooks/useOperations";
import { bytes, rub } from "@/lib/format";
export function MediaGalleryPage({ workspaceId: ws }: { workspaceId: string }) {
  const input = useRef<HTMLInputElement>(null),
    [tab, setTab] = useState("all"),
    [selected, setSelected] = useState<string | null>(null),
    [prompt, setPrompt] = useState(""),
    [generate, setGenerate] = useState(false);
  const query = useInfiniteQuery({
    queryKey: ["media", ws, tab],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => endpoints.media(ws, { tab, cursor: pageParam }),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  const detail = useQuery({
    queryKey: ["media-detail", ws, selected],
    queryFn: () => endpoints.mediaDetail(ws, selected!),
    enabled: !!selected,
  });
  const provider = useQuery({
    queryKey: ["image-provider", ws],
    queryFn: () => endpoints.imageProvider(ws),
  });
  const action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader
        title="Media gallery"
        actions={
          <>
            <Tooltip content={provider.data?.message || "Create an image"}>
              <span>
                <Button
                  disabled={!provider.data?.available}
                  onClick={() => setGenerate(true)}
                >
                  Generate image
                </Button>
              </span>
            </Tooltip>
            <Button
              variant="primary"
              onClick={() => input.current?.click()}
              loading={action.isPending}
            >
              Upload
            </Button>
            <input
              ref={input}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) action.mutate(() => endpoints.uploadMedia(ws, f));
                e.target.value = "";
              }}
            />
          </>
        }
      />
      <Tabs
        value={tab}
        onValueChange={setTab}
        tabs={[
          "all",
          "generated",
          "uploaded",
          "used",
          "unused",
          "archived",
        ].map((value) => ({
          value,
          label: value.charAt(0).toUpperCase() + value.slice(1),
        }))}
      />
      <Card className="p-4">
        {query.isPending ? (
          <SkeletonRows />
        ) : query.isError ? (
          <ErrorState error={query.error} />
        ) : !query.data.pages[0].items.length ? (
          <EmptyState
            title="No images here"
            description="Upload an image to use it in a post."
          />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {query.data.pages
              .flatMap((p) => p.items)
              .map((a) => (
                <button
                  className="overflow-hidden rounded-lg border text-left"
                  key={a.id}
                  onClick={() => setSelected(a.id)}
                >
                  <img
                    src={mediaUrl(a.url)}
                    alt={a.original_filename || "Generated image"}
                    loading="lazy"
                    className="aspect-square w-full object-cover"
                  />
                  <div className="p-2 text-xs space-y-1">
                    <p className="truncate">
                      {a.original_filename || "Generated image"}
                    </p>
                    <StatusBadge status={a.status} />
                    <p className="text-ink-faint">
                      {bytes(a.size_bytes)} · {a.used ? "Used" : "Unused"}
                    </p>
                  </div>
                </button>
              ))}
          </div>
        )}
        {query.hasNextPage && (
          <Button className="mt-4" onClick={() => void query.fetchNextPage()}>
            Load more
          </Button>
        )}
      </Card>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
        title="Image details"
      >
        {detail.data && (
          <div className="space-y-3">
            <img
              src={mediaUrl(detail.data.url)}
              alt={detail.data.original_filename || "Image"}
              className="w-full max-h-80 object-contain"
            />
            <p>
              {detail.data.width} × {detail.data.height} ·{" "}
              {bytes(detail.data.size_bytes)} · {rub(detail.data.cost_rub)}
            </p>
            <p>
              {detail.data.provider} {detail.data.model}
            </p>
            <p className="text-sm text-ink-muted">{detail.data.prompt}</p>
            {detail.data.linked_posts.map((p) => (
              <p key={p.id}>
                {p.title} · {p.status}
              </p>
            ))}
            <Button
              onClick={() =>
                action.mutate(() =>
                  endpoints.archiveMedia(
                    ws,
                    selected!,
                    detail.data!.status !== "ARCHIVED",
                  ),
                )
              }
            >
              {detail.data.status === "ARCHIVED" ? "Restore" : "Archive"}
            </Button>
            <a
              className="btn-secondary"
              href={mediaUrl(detail.data.url) + "?download=true"}
              download
            >
              Download
            </a>
          </div>
        )}
        {detail.isError && <ErrorState error={detail.error} />}
      </Dialog>
      <Dialog open={generate} onOpenChange={setGenerate} title="Generate image">
        <Textarea
          aria-label="Image prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <Button
          className="mt-3"
          disabled={prompt.trim().length < 3 || action.isPending}
          onClick={() => {
            action.mutate(() => endpoints.generateImage(ws, prompt));
            setGenerate(false);
          }}
        >
          Generate
        </Button>
      </Dialog>
    </div>
  );
}
