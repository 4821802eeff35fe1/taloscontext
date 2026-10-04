import { useLocation } from "@tanstack/react-router";
import { AppLink } from "@/components/ui/AppLink";
import clsx from "clsx";

type NavItem = { label: string; to: string };
type NavGroup = { title: string; items: NavItem[] };

const GROUPS: NavGroup[] = [
  { title: "", items: [{ label: "Overview", to: "/" }] },
  {
    title: "Content",
    items: [
      { label: "Posts", to: "/content" },
      { label: "Approval", to: "/approval" },
    ],
  },
  {
    title: "Distribution",
    items: [
      { label: "Channels", to: "/channels" },
      { label: "Channel Sets", to: "/channel-sets" },
      { label: "Accounts", to: "/accounts" },
    ],
  },
  { title: "Media", items: [{ label: "Gallery", to: "/media" }] },
  { title: "Analytics", items: [{ label: "Costs", to: "/costs" }] },
  {
    title: "Automation",
    items: [
      { label: "Autopilot", to: "/autopilot" },
      { label: "Jobs", to: "/jobs" },
    ],
  },
];

export function Sidebar() {
  const location = useLocation();

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-surface-border bg-surface px-3 py-4">
      <div className="mb-6 flex items-center gap-2 px-2">
        <div className="h-6 w-6 rounded-md bg-accent" />
        <span className="text-sm font-semibold tracking-tight">ChannelOS</span>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto">
        {GROUPS.map((group) => (
          <div key={group.title || "root"}>
            {group.title && (
              <div className="mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                {group.title}
              </div>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = location.pathname === item.to;
                return (
                  <AppLink
                    key={item.to}
                    to={item.to}
                    className={clsx(
                      "block rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                      active
                        ? "bg-accent/15 text-accent-foreground font-medium"
                        : "text-ink-muted hover:bg-surface-overlay hover:text-ink",
                    )}
                  >
                    {item.label}
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
