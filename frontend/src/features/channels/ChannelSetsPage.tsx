import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { Card, EmptyState } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Select } from "@/components/ui/Select";
import { Plus } from "@/components/ui/icons";

const MODE_OPTIONS = [
  { value: "EXACT", label: "Exact — same text everywhere" },
  { value: "CTA_PER_CHANNEL", label: "CTA per channel" },
  { value: "CONTACT_PER_CHANNEL", label: "Contact per channel" },
  { value: "ADAPTED", label: "Adapted — AI rewrites per channel" },
];

function CreateChannelSetDialog({ workspaceId, open, onOpenChange }: { workspaceId: string; open: boolean; onOpenChange: (v: boolean) => void }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [mode, setMode] = useState("EXACT");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const channels = useQuery({ queryKey: ["channels", workspaceId], queryFn: () => endpoints.channels(workspaceId) });

  const create = useMutation({
    mutationFn: () =>
      endpoints.createChannelSet(workspaceId, {
        name,
        description: "",
        mode,
        channel_ids: Array.from(selected),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["channel-sets", workspaceId] });
      onOpenChange(false);
      setName("");
      setSelected(new Set());
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Create channel set" description="Group channels that receive the same content.">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div>
          <label className="label">Name</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} required placeholder="Talos Network" />
        </div>
        <div>
          <label className="label">Distribution mode</label>
          <Select value={mode} onValueChange={setMode} options={MODE_OPTIONS} />
        </div>
        <div>
          <label className="label">Channels ({selected.size} selected)</label>
          <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-surface-border p-2">
            {channels.data?.map((c) => (
              <label key={c.id} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-overlay">
                <input
                  type="checkbox"
                  checked={selected.has(c.id)}
                  onChange={(e) => {
                    const next = new Set(selected);
                    if (e.target.checked) next.add(c.id);
                    else next.delete(c.id);
                    setSelected(next);
                  }}
                />
                {c.title}
              </label>
            ))}
          </div>
        </div>
        <button className="btn-primary w-full" disabled={create.isPending || selected.size === 0}>
          Create channel set
        </button>
      </form>
    </Dialog>
  );
}

export function ChannelSetsPage({ workspaceId }: { workspaceId: string }) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const channelSets = useQuery({ queryKey: ["channel-sets", workspaceId], queryFn: () => endpoints.channelSets(workspaceId) });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Channel sets</h1>
        <button className="btn-primary" onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" /> New channel set
        </button>
      </div>

      <Card>
        {channelSets.data && channelSets.data.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {channelSets.data.map((set) => (
              <div key={set.id} className="rounded-lg border border-surface-border p-4">
                <p className="text-sm font-medium text-ink">{set.name}</p>
                <p className="text-xs text-ink-faint">{set.member_count} channels · {set.mode}</p>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No channel sets yet"
            description="Create a channel set to publish one piece of content to many channels at once."
            action={
              <button className="btn-primary" onClick={() => setDialogOpen(true)}>
                New channel set
              </button>
            }
          />
        )}
      </Card>

      <CreateChannelSetDialog workspaceId={workspaceId} open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
