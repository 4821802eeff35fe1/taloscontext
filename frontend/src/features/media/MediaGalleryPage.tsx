import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_BASE, endpoints } from "@/lib/api";
import { Card, EmptyState } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Plus } from "@/components/ui/icons";

export function MediaGalleryPage({ workspaceId }: { workspaceId: string }) {
  const client = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const media = useQuery({ queryKey: ["media", workspaceId], queryFn: () => endpoints.media(workspaceId) });

  const upload = useMutation({
    mutationFn: (file: File) => endpoints.uploadMedia(workspaceId, file),
    onSuccess: () => client.invalidateQueries({ queryKey: ["media", workspaceId] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Media gallery</h1>
        <button className="btn-primary" onClick={() => inputRef.current?.click()}>
          <Plus className="h-4 w-4" /> Upload
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload.mutate(file);
            e.target.value = "";
          }}
        />
      </div>

      <Card>
        {media.data && media.data.length > 0 ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {media.data.map((asset) => (
              <div key={asset.id} className="group relative overflow-hidden rounded-lg border border-surface-border">
                <img src={`${API_BASE}${asset.url}`} alt="" loading="lazy" className="aspect-square w-full object-cover" />
                <div className="absolute bottom-1 left-1">
                  <StatusBadge status={asset.status} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No media yet" description="Upload images or generate them from the Content Studio." />
        )}
      </Card>
    </div>
  );
}
