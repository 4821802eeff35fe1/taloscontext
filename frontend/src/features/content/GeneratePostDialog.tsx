import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, ApiError } from "@/lib/api";
import { Dialog } from "@/components/ui/Dialog";
import { Select } from "@/components/ui/Select";

export function GeneratePostDialog({
  workspaceId,
  open,
  onOpenChange,
  onCreated,
}: {
  workspaceId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: (contentId: string) => void;
}) {
  const client = useQueryClient();
  const [instruction, setInstruction] = useState("");
  const [channelSetId, setChannelSetId] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  const channelSets = useQuery({ queryKey: ["channel-sets", workspaceId], queryFn: () => endpoints.channelSets(workspaceId) });

  const generate = useMutation({
    mutationFn: () => endpoints.generateContent(workspaceId, { instruction, channel_set_id: channelSetId ?? null }),
    onSuccess: (item) => {
      client.invalidateQueries({ queryKey: ["content", workspaceId] });
      onOpenChange(false);
      setInstruction("");
      onCreated(item.id);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Generation failed"),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Generate with AI"
      description="One AI call produces the post; it's then distributed to every channel in the chosen set without regenerating."
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          generate.mutate();
        }}
      >
        <div>
          <label className="label">Instruction</label>
          <textarea
            className="input min-h-[90px]"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="E.g. Write an educational post about improving CTR in media buying"
            required
          />
        </div>
        <div>
          <label className="label">Target channel set (optional)</label>
          <Select
            value={channelSetId}
            onValueChange={setChannelSetId}
            placeholder="Choose later"
            options={(channelSets.data ?? []).map((s) => ({ value: s.id, label: s.name }))}
          />
        </div>
        {error && <p className="text-sm text-danger">{error}</p>}
        <button className="btn-primary w-full" disabled={generate.isPending}>
          {generate.isPending ? "Generating…" : "Generate post"}
        </button>
      </form>
    </Dialog>
  );
}
