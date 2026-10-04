import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
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
  const anyFake = data.text_provider_is_fake || data.image_provider_is_fake || data.telegram_provider_is_fake;
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

  return (
    <div className="flex">
      <Sidebar />
      <div className="flex-1">
        <header className="flex items-center justify-between border-b border-surface-border px-6 py-3">
          <div className="w-64">
            {workspaces && workspaces.length > 0 && (
              <Select
                value={workspaceId ?? undefined}
                onValueChange={setWorkspaceId}
                options={workspaces.map((w) => ({ value: w.id, label: w.name }))}
                placeholder="Select workspace"
              />
            )}
          </div>
          <button className="btn-ghost" onClick={() => logout()}>
            Sign out
          </button>
        </header>
        {workspaceId && <FakeProviderBanner workspaceId={workspaceId} />}
        <main className="px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
