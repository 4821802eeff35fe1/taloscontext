import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { Dialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";
export function CommandPalette({
  ws,
  open,
  onOpenChange,
}: {
  ws: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [q, setQ] = useState(""),
    [debounced, setDebounced] = useState("");
  const navigate = useNavigate(),
    action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 200);
    return () => clearTimeout(t);
  }, [q]);
  const results = useQuery({
    queryKey: ["search", ws, debounced],
    queryFn: () => endpoints.search(ws, debounced),
    enabled: debounced.length > 1,
  });
  const go = (to: string) => {
    onOpenChange(false);
    void navigate({ to });
  };
  const itemClass =
    "cursor-pointer rounded-md px-3 py-2 text-sm text-ink-muted data-[selected=true]:bg-surface-hover data-[selected=true]:text-ink";
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Commands and search">
      <Command label="Search commands and posts" shouldFilter={false} loop>
        <Command.Input
          aria-label="Search commands and posts"
          placeholder="Search posts, channels, channel sets…"
          value={q}
          onValueChange={setQ}
          className="input mb-3"
        />
        <Command.List className="max-h-80 overflow-auto">
          <Command.Empty>No matching results.</Command.Empty>
          <Command.Group heading="Actions">
            {[
              ["Create post", "/content?create=1"],
              ["Generate post", "/content?generate=1"],
              ["Open Calendar", "/calendar"],
              ["Add Telegram account", "/accounts?add=1"],
              ["Create Channel Set", "/channel-sets?create=1"],
              ["Open Approval", "/approval"],
              ["Open Jobs", "/jobs"],
              ["Open Costs", "/costs"],
            ]
              .filter(
                ([label]) =>
                  !q || label.toLowerCase().includes(q.toLowerCase()),
              )
              .map(([label, to]) => (
                <Command.Item
                  className={itemClass}
                  key={label}
                  onSelect={() => go(to)}
                >
                  {label}
                </Command.Item>
              ))}
            {(!q || "pause autopilot".includes(q.toLowerCase())) && (
              <Command.Item
                className={itemClass}
                onSelect={() => {
                  action.mutate(() =>
                    endpoints.updateAutopilot(ws, { mode: "MANUAL" }),
                  );
                  onOpenChange(false);
                }}
              >
                Pause Autopilot
              </Command.Item>
            )}
          </Command.Group>
          <Command.Group heading="Search results">
            {results.data?.map((r) => (
              <Command.Item
                key={r.kind + r.id}
                className={itemClass}
                onSelect={() =>
                  go(
                    r.kind === "post"
                      ? `/content?post=${r.id}`
                      : r.kind === "channel"
                        ? "/channels"
                        : `/channel-sets?set=${r.id}`,
                  )
                }
              >
                {r.title}
                <span className="ml-2 text-xs text-ink-faint">
                  {r.kind} · {r.subtitle}
                </span>
              </Command.Item>
            ))}
          </Command.Group>
        </Command.List>
      </Command>
    </Dialog>
  );
}
