import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { CommandPalette } from "./CommandPalette";
import { useRealtime } from "@/hooks/useRealtime";
import { AppLink } from "@/components/ui/AppLink";
import { Sidebar } from "./Sidebar";
import { useLogout, useWorkspaces } from "@/hooks/useSession";
import { useWorkspaceStore } from "@/stores/workspace";
import { endpoints } from "@/lib/api";
import { Select } from "@/components/ui/Select";

function FakeProviderBanner({ workspaceId }: { workspaceId: string }) {
  const { data } = useQuery({
    queryKey: ["ai-status", workspaceId],
    queryFn: () => endpoints.aiStatus(workspaceId),
  });
  if (!data) return null;
  const anyFake =
    data.text_provider_is_fake ||
    data.image_provider_is_fake ||
    data.telegram_provider_is_fake;
  if (!anyFake) return null;

  return (
    <div className="border-b border-warning/30 bg-warning/10 px-6 py-1.5 text-xs text-warning">
      Dev mode: fake providers active —{" "}
      {[
        data.text_provider_is_fake && "AI text",
        data.image_provider_is_fake && "AI image",
        data.telegram_provider_is_fake && "Telegram",
      ]
        .filter(Boolean)
        .join(", ")}{" "}
      are simulated. No real cost, no real sends.
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { data: workspaces } = useWorkspaces();
  const { workspaceId, setWorkspaceId } = useWorkspaceStore();
  const logout = useLogout();
  const [mobile, setMobile] = useState(false),
    [commands, setCommands] = useState(false);
  const connected = useRealtime(workspaceId);
  const notifications = useQuery({
    queryKey: ["notifications", workspaceId],
    queryFn: () => endpoints.notifications(workspaceId!),
    enabled: !!workspaceId,
    refetchInterval: 30000,
  });
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommands((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div className="flex">
      <div className="hidden lg:block">
        <Sidebar />
      </div>
      {mobile && (
        <div
          className="fixed inset-0 z-30 bg-black/60"
          onClick={() => setMobile(false)}
        >
          <div className="w-56 bg-surface" onClick={(e) => e.stopPropagation()}>
            <button className="btn-ghost" onClick={() => setMobile(false)}>
              Close navigation
            </button>
            <Sidebar />
          </div>
        </div>
      )}
      <div className="flex-1 min-w-0">
        <header className="flex items-center justify-between border-b border-surface-border px-6 py-3">
          <button
            className="btn-ghost lg:hidden"
            aria-label="Open navigation"
            onClick={() => setMobile(true)}
          >
            ☰
          </button>
          <div className="w-40 sm:w-56">
            {workspaces && workspaces.length > 0 && (
              <Select
                value={workspaceId ?? undefined}
                onValueChange={setWorkspaceId}
                options={workspaces.map((w) => ({
                  value: w.id,
                  label: w.name,
                }))}
                placeholder="Select workspace"
              />
            )}
          </div>
          <div className="flex items-center gap-1 flex-wrap">
            <span className="hidden xl:inline text-xs text-ink-faint">
              {connected ? "Live" : "Reconnecting…"}
            </span>
            <button className="btn-ghost" onClick={() => setCommands(true)}>
              ⌘K
            </button>
            <AppLink
              className="btn-ghost"
              to="/notifications"
              aria-label="Notifications"
            >
              Inbox {notifications.data?.unread || ""}
            </AppLink>
            <button className="btn-ghost" onClick={() => logout()}>
              Sign out
            </button>
          </div>
        </header>
        {workspaceId && <FakeProviderBanner workspaceId={workspaceId} />}
        <main className="px-3 py-5 sm:px-6">{children}</main>
        {workspaceId && (
          <CommandPalette
            ws={workspaceId}
            open={commands}
            onOpenChange={setCommands}
          />
        )}
      </div>
    </div>
  );
}
