import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints } from "@/lib/api";
import { channelSetModeLabel, statusLabel } from "@/i18n/labels";
import { Dialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";

const ACTIONS: [key: string, to: string][] = [
  ["createPost", "/content?create=1"],
  ["generatePost", "/content?generate=1"],
  ["openCalendar", "/calendar"],
  ["addAccount", "/accounts?add=1"],
  ["createChannelSet", "/channel-sets?create=1"],
  ["openApproval", "/approval"],
  ["openJobs", "/jobs"],
  ["openCosts", "/costs"],
];

export function CommandPalette({
  ws,
  open,
  onOpenChange,
}: {
  ws: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const { t } = useTranslation();
  const [q, setQ] = useState(""),
    [debounced, setDebounced] = useState("");
  const navigate = useNavigate(),
    action = useOperation(ws, (fn: () => Promise<unknown>) => fn(), t("palette.autopilotPaused"));
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(q), 200);
    return () => clearTimeout(timer);
  }, [q]);
  const results = useQuery({
    queryKey: ["search", ws, debounced],
    queryFn: () => endpoints.search(ws, debounced),
    enabled: debounced.length > 1,
  });
  const go = (to: string) => {
    onOpenChange(false);
    void navigate({
      to: to.includes("?") ? `${to}&action_id=${Date.now()}` : to,
    });
  };
  const matches = (label: string) => !q || label.toLowerCase().includes(q.toLowerCase());
  const itemClass =
    "cursor-pointer rounded-md px-3 py-2 text-sm text-ink-muted data-[selected=true]:bg-surface-hover data-[selected=true]:text-ink";
  const pauseLabel = t("palette.action.pauseAutopilot");
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t("palette.title")}>
      <Command label={t("palette.placeholder")} shouldFilter={false} loop>
        <Command.Input
          aria-label={t("palette.placeholder")}
          placeholder={t("palette.placeholder")}
          value={q}
          onValueChange={setQ}
          className="input mb-3"
        />
        <Command.List className="max-h-80 overflow-auto">
          <Command.Empty>{t("palette.empty")}</Command.Empty>
          <Command.Group heading={t("palette.actions")}>
            {ACTIONS.map(([key, to]) => [t(`palette.action.${key}`), to] as const)
              .filter(([label]) => matches(label))
              .map(([label, to]) => (
                <Command.Item className={itemClass} key={to} onSelect={() => go(to)}>
                  {label}
                </Command.Item>
              ))}
            {matches(pauseLabel) && (
              <Command.Item
                className={itemClass}
                onSelect={() => {
                  action.mutate(() => endpoints.updateAutopilot(ws, { mode: "MANUAL" }));
                  onOpenChange(false);
                }}
              >
                {pauseLabel}
              </Command.Item>
            )}
          </Command.Group>
          <Command.Group heading={t("palette.results")}>
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
                {r.title || t("untitled")}
                <span className="ml-2 text-xs text-ink-faint">
                  {[
                    t(`palette.kind.${r.kind}`),
                    r.status && (r.kind === "post" ? statusLabel(r.status, "content") : channelSetModeLabel(r.status)),
                    r.subtitle,
                  ].filter(Boolean).join(" · ")}
                </span>
              </Command.Item>
            ))}
          </Command.Group>
        </Command.List>
      </Command>
    </Dialog>
  );
}
