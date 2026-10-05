import { useLocation } from "@tanstack/react-router";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { AppLink } from "@/components/ui/AppLink";

type NavItem = { key: string; to: string };
type NavGroup = { key: string; items: NavItem[] };

// Labels live in common.json under nav.* — the structure here is language-neutral.
export const NAV_GROUPS: NavGroup[] = [
  { key: "", items: [{ key: "overview", to: "/" }] },
  {
    key: "content",
    items: [
      { key: "posts", to: "/content" },
      { key: "approval", to: "/approval" },
      { key: "calendar", to: "/calendar" },
      { key: "series", to: "/series" },
      { key: "ideas", to: "/ideas" },
    ],
  },
  {
    key: "distribution",
    items: [
      { key: "channels", to: "/channels" },
      { key: "channelSets", to: "/channel-sets" },
      { key: "accounts", to: "/accounts" },
    ],
  },
  { key: "media", items: [{ key: "gallery", to: "/media" }] },
  {
    key: "ai",
    items: [
      { key: "knowledge", to: "/knowledge" },
      { key: "tone", to: "/tone" },
      { key: "sources", to: "/sources" },
    ],
  },
  {
    key: "analytics",
    items: [
      { key: "performance", to: "/performance" },
      { key: "costs", to: "/costs" },
    ],
  },
  {
    key: "automation",
    items: [
      { key: "autopilot", to: "/autopilot" },
      { key: "schedules", to: "/schedules" },
      { key: "jobs", to: "/jobs" },
    ],
  },
  {
    key: "system",
    items: [
      { key: "notifications", to: "/notifications" },
      { key: "audit", to: "/audit" },
      { key: "settings", to: "/settings" },
    ],
  },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const location = useLocation();
  const { t } = useTranslation();

  return (
    <aside className="sticky top-0 flex h-dvh w-60 shrink-0 flex-col border-r border-surface-border bg-surface px-3 py-4">
      <div className="mb-6 flex items-center gap-2 px-2">
        <div className="h-6 w-6 rounded-md bg-accent" />
        <span className="text-sm font-semibold tracking-tight">ChannelOS</span>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto" aria-label={t("nav.label")}>
        {NAV_GROUPS.map((group) => (
          <div key={group.key || "root"}>
            {group.key && (
              <div className="mb-1.5 truncate px-2 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                {t(`nav.group.${group.key}`)}
              </div>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = location.pathname === item.to;
                return (
                  <AppLink
                    key={item.to}
                    to={item.to}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={clsx(
                      "block truncate rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                      active
                        ? "bg-accent/15 font-medium text-accent-foreground"
                        : "text-ink-muted hover:bg-surface-overlay hover:text-ink",
                    )}
                  >
                    {t(`nav.item.${item.key}`)}
                  </AppLink>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
