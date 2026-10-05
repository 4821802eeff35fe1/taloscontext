import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Bell, Check, Command as CommandIcon, Languages, LogOut, Menu, X } from "lucide-react";
import { CommandPalette } from "./CommandPalette";
import { useRealtime } from "@/hooks/useRealtime";
import { AppLink } from "@/components/ui/AppLink";
import { Sidebar } from "./Sidebar";
import { useLogout, useWorkspaces } from "@/hooks/useSession";
import { useLanguage } from "@/hooks/useLanguage";
import { useWorkspaceStore } from "@/stores/workspace";
import { endpoints } from "@/lib/api";
import { Select } from "@/components/ui/forms";
import { DropdownMenu } from "@/components/ui/overlays";
import { SUPPORTED_LANGUAGES } from "@/i18n";

function FakeProviderBanner({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["ai-status", workspaceId],
    queryFn: () => endpoints.aiStatus(workspaceId),
  });
  if (!data) return null;
  const parts = [
    data.text_provider_is_fake && t("shell.fake.aiText"),
    data.image_provider_is_fake && t("shell.fake.aiImage"),
    data.telegram_provider_is_fake && "Telegram",
  ].filter(Boolean) as string[];
  if (!parts.length) return null;

  return (
    <div className="border-b border-warning/30 bg-warning/10 px-6 py-1.5 text-xs text-warning">
      {t("shell.fake.banner", {
        providers: new Intl.ListFormat(t("shell.listLocale"), { type: "conjunction" }).format(parts),
      })}
    </div>
  );
}

export function UserMenu() {
  const { t } = useTranslation();
  const logout = useLogout();
  const { language, setLanguage } = useLanguage();
  return (
    <DropdownMenu
      trigger={
        <button className="btn-ghost" aria-label={t("shell.userMenu")}>
          <Languages className="h-4 w-4" aria-hidden />
          <span className="hidden sm:inline">{t(`language.short.${language}`)}</span>
        </button>
      }
      items={[
        { type: "label", label: t("language.label") },
        ...SUPPORTED_LANGUAGES.map((lang) => ({
          label: t(`language.name.${lang}`),
          icon: lang === language ? Check : undefined,
          onSelect: () => setLanguage(lang),
        })),
        { type: "separator" as const },
        { label: t("shell.signOut"), icon: LogOut, onSelect: () => void logout() },
      ]}
    />
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { data: workspaces } = useWorkspaces();
  const { workspaceId, setWorkspaceId } = useWorkspaceStore();
  const [mobile, setMobile] = useState(false),
    [commands, setCommands] = useState(false);
  const connected = useRealtime(workspaceId);
  const notifications = useQuery({
    queryKey: ["notifications", workspaceId],
    queryFn: () => endpoints.notifications(workspaceId!),
    enabled: !!workspaceId,
    refetchInterval: 30000,
  });
  const unread = notifications.data?.unread ?? 0;
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
        <div className="fixed inset-0 z-30 bg-black/60" onClick={() => setMobile(false)}>
          <div className="relative w-60 bg-surface" onClick={(e) => e.stopPropagation()}>
            <button
              className="btn-ghost absolute right-2 top-3 z-10"
              aria-label={t("shell.closeNavigation")}
              onClick={() => setMobile(false)}
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
            <Sidebar onNavigate={() => setMobile(false)} />
          </div>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <header className="flex items-center justify-between gap-2 border-b border-surface-border px-3 py-3 sm:px-6">
          <button className="btn-ghost lg:hidden" aria-label={t("shell.openNavigation")} onClick={() => setMobile(true)}>
            <Menu className="h-4 w-4" aria-hidden />
          </button>
          <div className="w-40 min-w-0 sm:w-56">
            {workspaces && workspaces.length > 0 && (
              <Select
                value={workspaceId ?? undefined}
                onValueChange={setWorkspaceId}
                options={workspaces.map((w) => ({ value: w.id, label: w.name }))}
                placeholder={t("shell.selectWorkspace")}
                ariaLabel={t("shell.workspace")}
              />
            )}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-1">
            <span className="hidden text-xs text-ink-faint xl:inline" aria-live="polite">
              {connected ? t("shell.live") : t("shell.reconnecting")}
            </span>
            <button className="btn-ghost" onClick={() => setCommands(true)} aria-label={t("palette.open")}>
              <CommandIcon className="h-4 w-4" aria-hidden />
              <span className="hidden sm:inline">K</span>
            </button>
            <AppLink
              className="btn-ghost"
              to="/notifications"
              aria-label={t("shell.notifications", { count: unread })}
            >
              <Bell className="h-4 w-4" aria-hidden />
              {unread > 0 && (
                <span className="rounded-full bg-accent px-1.5 text-2xs font-semibold tabular-nums text-white">{unread}</span>
              )}
            </AppLink>
            <UserMenu />
          </div>
        </header>
        {workspaceId && <FakeProviderBanner workspaceId={workspaceId} />}
        <main className="px-3 py-5 sm:px-6">{children}</main>
        {workspaceId && <CommandPalette ws={workspaceId} open={commands} onOpenChange={setCommands} />}
      </div>
    </div>
  );
}
