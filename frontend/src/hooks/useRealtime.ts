import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE } from "@/lib/api";
export function eventQueryPrefixes(type: string): string[] {
  if (type.startsWith("job."))
    return [
      "jobs",
      "job",
      "content",
      "content-item",
      "dashboard",
      "ideas",
      "sources",
      "costs",
    ];
  if (type.startsWith("content."))
    return [
      "content",
      "content-item",
      "revisions",
      "context",
      "content-costs",
      "calendar",
      "series",
      "dashboard",
      "costs",
      "audit",
    ];
  if (type.startsWith("publication."))
    return [
      "batches",
      "content",
      "calendar",
      "dashboard",
      "channels",
      "channel-sets",
      "audit",
    ];
  if (type.startsWith("telegram."))
    return ["telegram-accounts", "channels", "channel-sets", "dashboard"];
  if (type.startsWith("budget.")) return ["costs", "notifications"];
  if (type === "media.created")
    return ["media", "content-item", "content-costs", "costs"];
  return ["notifications"];
}
export function useRealtime(workspaceId: string | null) {
  const client = useQueryClient();
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (!workspaceId) return;
    let stream: EventSource | undefined,
      timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false,
      attempt = 0;
    const refresh = () =>
      void client.invalidateQueries({
        predicate: (q) => q.queryKey.includes(workspaceId),
      });
    const connect = () => {
      stream = new EventSource(
        `${API_BASE}/api/v1/workspaces/${workspaceId}/events`,
        { withCredentials: true },
      );
      stream.addEventListener("ready", () => {
        attempt = 0;
        setConnected(true);
        refresh();
      });
      stream.onmessage = (event) => {
        try {
          const { type } = JSON.parse(event.data) as { type: string };
          const prefixes = eventQueryPrefixes(type);
          void client.invalidateQueries({
            predicate: (q) =>
              q.queryKey.includes(workspaceId) &&
              prefixes.includes(String(q.queryKey[0])),
          });
        } catch {
          /* ignore malformed transport frames */
        }
      };
      stream.onerror = () => {
        stream?.close();
        setConnected(false);
        if (!stopped)
          timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** attempt++));
      };
    };
    connect();
    window.addEventListener("online", refresh);
    return () => {
      stopped = true;
      stream?.close();
      clearTimeout(timer);
      window.removeEventListener("online", refresh);
    };
  }, [workspaceId, client]);
  return connected;
}
