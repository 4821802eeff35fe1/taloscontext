import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, type Role, type Settings } from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  SkeletonRows,
  Textarea,
} from "@/components/ui/primitives";
import { Select, Tabs } from "@/components/ui/forms";
import { ConfirmDialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";
import { dateTime, timezoneOptions } from "@/lib/format";
import { auditActionLabel, entityLabel, misfirePolicyLabel, notificationText, roleLabel } from "@/i18n/labels";
export function AuditPage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("system");
  const [q, setQ] = useState(""),
    [action, setAction] = useState("all"),
    [actor, setActor] = useState("all"),
    [entity, setEntity] = useState("all"),
    [since, setSince] = useState(""),
    [until, setUntil] = useState("");
  const members = useQuery({
    queryKey: ["members", ws],
    queryFn: () => endpoints.members(ws),
  });
  const query = useInfiniteQuery({
    queryKey: ["audit", ws, q, action, actor, entity, since, until],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      endpoints.audit(ws, {
        q,
        action: action === "all" ? undefined : action,
        actor_id: actor === "all" ? undefined : actor,
        entity_type: entity === "all" ? undefined : entity,
        since: since ? since + "T00:00:00Z" : undefined,
        until: until ? until + "T23:59:59Z" : undefined,
        cursor: pageParam,
      }),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  return (
    <div className="space-y-4">
      <PageHeader title={t("audit.title")} description={t("audit.description")} />
      <div className="flex flex-wrap gap-2">
        <Input
          aria-label={t("audit.searchAria")}
          placeholder={t("audit.search")}
          className="max-w-xs"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select
          className="w-60"
          ariaLabel={t("audit.actionAria")}
          value={action}
          onValueChange={setAction}
          options={[
            { value: "all", label: t("audit.allActions") },
            ...(query.data?.pages[0].actions ?? []).map((value) => ({
              value,
              label: auditActionLabel(value),
            })),
          ]}
        />
        <Select
          className="w-52"
          ariaLabel={t("audit.actorAria")}
          value={actor}
          onValueChange={setActor}
          options={[
            { value: "all", label: t("audit.allUsers") },
            ...(members.data ?? []).map((m) => ({
              value: m.user_id,
              label: m.full_name || m.email,
            })),
          ]}
        />
        <Select
          className="w-44"
          ariaLabel={t("audit.entityAria")}
          value={entity}
          onValueChange={setEntity}
          options={[
            "all",
            "content",
            "workspace",
            "publication",
            "job",
            "telegram_account",
            "channel_set",
            "source",
            "schedule",
            "knowledge",
            "tone",
          ].map((value) => ({
            value,
            label: value === "all" ? "All entities" : value,
          }))}
        />
        <Input
          aria-label={t("audit.fromAria")}
          placeholder={t("audit.fromPlaceholder")}
          className="w-44"
          value={since}
          onChange={(e) => setSince(e.target.value)}
        />
        <Input
          aria-label={t("audit.untilAria")}
          placeholder={t("audit.untilPlaceholder")}
          className="w-44"
          value={until}
          onChange={(e) => setUntil(e.target.value)}
        />
      </div>
      <Card>
        {query.isPending ? (
          <SkeletonRows />
        ) : query.isError ? (
          <ErrorState error={query.error} />
        ) : !query.data.pages[0].items.length ? (
          <EmptyState title={t("audit.empty")} />
        ) : (
          query.data.pages
            .flatMap((p) => p.items)
            .map((e) => (
              <details key={e.id} className="border-b p-4">
                <summary className="cursor-pointer flex flex-wrap justify-between gap-2">
                  <span>
                    {e.actor_name} · {auditActionLabel(e.action)}
                  </span>
                  <span className="text-xs text-ink-muted">
                    {dateTime(e.created_at)}
                  </span>
                </summary>
                <p className="mt-2 text-xs text-ink-faint">
                  {e.entity_type} · {e.entity_id}
                </p>
                <pre className="mt-2 overflow-auto text-xs">
                  {JSON.stringify(e.metadata, null, 2)}
                </pre>
              </details>
            ))
        )}
        {query.hasNextPage && (
          <Button className="m-4" onClick={() => void query.fetchNextPage()}>
            Load more
          </Button>
        )}
      </Card>
    </div>
  );
}
export function NotificationsPage({
  workspaceId: ws,
}: {
  workspaceId: string;
}) {
  const { t } = useTranslation("system");
  const [unread, setUnread] = useState("all");
  const query = useQuery({
    queryKey: ["notifications", ws, unread],
    queryFn: () => endpoints.notifications(ws, unread === "unread"),
    refetchInterval: 30000,
  });
  const action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader
        title={t("notifications.title")}
        actions={
          <Button
            onClick={() =>
              action.mutate(() => endpoints.readAllNotifications(ws))
            }
          >
            Mark all read
          </Button>
        }
      />
      <Select
        className="w-44"
        ariaLabel={t("notifications.filterAria")}
        value={unread}
        onValueChange={setUnread}
        options={[
          { value: "all", label: t("notifications.all") },
          { value: "unread", label: t("notifications.unread") },
        ]}
      />
      <Card>
        {query.isPending ? (
          <SkeletonRows />
        ) : query.isError ? (
          <ErrorState error={query.error} />
        ) : !query.data.items.length ? (
          <EmptyState title={t("notifications.empty")} />
        ) : (
          query.data.items.map((n) => (
            <div
              key={n.id}
              className={`p-4 border-b flex flex-wrap justify-between gap-3 ${n.read ? "" : "bg-accent/5"}`}
            >
              <div>
                <p>
                  {!n.read && "● "}
                  {notificationText(n)}
                </p>
                <p className="text-xs text-ink-faint mt-1">
                  {dateTime(n.created_at)}
                </p>
              </div>
              {!n.read && (
                <Button
                  size="sm"
                  onClick={() =>
                    action.mutate(() => endpoints.readNotification(ws, n.id))
                  }
                >
                  Mark read
                </Button>
              )}
            </div>
          ))
        )}
      </Card>
    </div>
  );
}
export function SettingsPage({ workspaceId: ws }: { workspaceId: string }) {
  const query = useQuery({
    queryKey: ["settings", ws],
    queryFn: () => endpoints.settings(ws),
  });
  if (query.isPending) return <SkeletonRows />;
  if (query.isError) return <ErrorState error={query.error} />;
  return <SettingsEditor key={ws} ws={ws} settings={query.data} />;
}
function SettingsEditor({
  ws,
  settings: s,
}: {
  ws: string;
  settings: Settings;
}) {
  const { t } = useTranslation("settings");
  const { t: ts } = useTranslation("system");
  const [tab, setTab] = useState("general"),
    [general, setGeneral] = useState(s.general),
    [budget, setBudget] = useState(s.budget),
    [muted, setMuted] = useState(
      (s.notifications.muted_kinds ?? []).join("\n"),
    ),
    [email, setEmail] = useState(""),
    [role, setRole] = useState<Role>("VIEWER"),
    [revoke, setRevoke] = useState(false);
  const sessions = useQuery({
      queryKey: ["sessions"],
      queryFn: endpoints.sessions,
      enabled: tab === "security",
    }),
    members = useQuery({
      queryKey: ["members", ws],
      queryFn: () => endpoints.members(ws),
    });
  const action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader title={t("title")} />
      <Tabs
        value={tab}
        onValueChange={setTab}
        tabs={[
          "general",
          "telegram",
          "ai",
          "budget",
          "storage",
          "security",
          "notifications",
        ].map((value) => ({
          value,
          label: value.charAt(0).toUpperCase() + value.slice(1),
        }))}
      />
      <Card className="p-5 max-w-3xl space-y-4">
        {tab === "general" && (
          <>
            <Field label={t("workspaceName")}>
              <Input
                aria-label={t("workspaceNameAria")}
                value={general.workspace_name}
                onChange={(e) =>
                  setGeneral({ ...general, workspace_name: e.target.value })
                }
              />
            </Field>
            <Select
              ariaLabel="Workspace timezone"
              value={general.timezone}
              onValueChange={(timezone) => setGeneral({ ...general, timezone })}
              options={timezoneOptions(general.timezone)}
            />
            <Select
              ariaLabel={t("defaultMisfireAria")}
              value={general.misfire_policy}
              onValueChange={(misfire_policy) =>
                setGeneral({ ...general, misfire_policy })
              }
              options={[
                "SKIP",
                "PUBLISH_IMMEDIATELY",
                "RESCHEDULE_NEXT_SLOT",
              ].map((value) => ({ value, label: misfirePolicyLabel(value) }))}
            />
            <Field label={t("misfireGrace")}>
              <Input
                type="number"
                min={1}
                value={general.misfire_grace_minutes}
                onChange={(e) =>
                  setGeneral({
                    ...general,
                    misfire_grace_minutes: Number(e.target.value),
                  })
                }
              />
            </Field>
            {general.cta_keys.map((k) => (
              <Field key={k} label={"CTA: " + k}>
                <Input
                  aria-label={`CTA ${k}`}
                  value={general.cta_defaults[k] ?? ""}
                  onChange={(e) =>
                    setGeneral({
                      ...general,
                      cta_defaults: {
                        ...general.cta_defaults,
                        [k]: e.target.value,
                      },
                    })
                  }
                />
              </Field>
            ))}
            <Button
              variant="primary"
              loading={action.isPending}
              onClick={() =>
                action.mutate(() =>
                  endpoints.updateGeneralSettings(ws, general),
                )
              }
            >
              Save general settings
            </Button>
            <h2 className="pt-4 font-medium">{t("members")}</h2>
            {members.data?.map((m) => (
              <div
                key={m.user_id}
                className="flex flex-wrap items-center gap-2"
              >
                <span className="flex-1">{m.full_name || m.email}</span>
                <Select
                  ariaLabel={`Role for ${m.email}`}
                  value={m.role}
                  onValueChange={(v) =>
                    action.mutate(() =>
                      endpoints.changeRole(ws, m.user_id, v as Role),
                    )
                  }
                  className="w-40"
                  options={[
                    "OWNER",
                    "ADMIN",
                    "EDITOR",
                    "APPROVER",
                    "VIEWER",
                  ].map((value) => ({ value, label: value }))}
                />
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              <Input
                aria-label={t("memberEmailAria")}
                className="max-w-xs"
                type="email"
                placeholder={t("memberEmailPlaceholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Select
                ariaLabel={t("newMemberRoleAria")}
                value={role}
                onValueChange={(v) => setRole(v as Role)}
                className="w-40"
                options={["ADMIN", "EDITOR", "APPROVER", "VIEWER"].map(
                  (value) => ({ value, label: value }),
                )}
              />
              <Button
                disabled={!email}
                onClick={() =>
                  action.mutate(() => endpoints.addMember(ws, email, role))
                }
              >
                Add member
              </Button>
            </div>
          </>
        )}
        {tab === "budget" && (
          <>
            {(Object.keys(budget) as (keyof typeof budget)[]).map((k) => (
              <Field label={k.replaceAll("_", " ")} key={k}>
                <Input
                  aria-label={k}
                  type="number"
                  min={0}
                  value={budget[k]}
                  onChange={(e) =>
                    setBudget({
                      ...budget,
                      [k]:
                        k === "budget_warning_pct"
                          ? Number(e.target.value)
                          : e.target.value,
                    })
                  }
                />
              </Field>
            ))}
            <Button
              variant="primary"
              onClick={() =>
                action.mutate(() => endpoints.updateBudget(ws, budget))
              }
            >
              Save budget
            </Button>
          </>
        )}
        {tab === "ai" && (
          <>
            <p>Text provider: {s.ai.text_provider}</p>
            <p className="break-all text-sm text-ink-muted">
              {s.ai.agent_base_url}
            </p>
            <p>API key: {s.ai.agent_api_key || "Not configured"}</p>
            <p>Model: {s.ai.model}</p>
            <p>
              Image: {s.ai.image_provider} · {s.ai.image_provider_status}
            </p>
            <p>Gateway key: {s.ai.gateway_api_key || "Not configured"}</p>
            {Object.entries(s.ai.pricing).map(([k, v]) => (
              <p key={k} className="text-sm">
                {k}: {v} ₽ / million tokens
              </p>
            ))}
          </>
        )}
        {tab === "telegram" && (
          <>
            {Object.entries(s.telegram).map(([k, v]) => (
              <p key={k}>
                {k.replaceAll("_", " ")}: {v ? ts("yes") : ts("no")}
              </p>
            ))}
          </>
        )}
        {tab === "storage" && (
          <>
            <p>Endpoint: {s.storage.endpoint_host}</p>
            <p>Bucket: {s.storage.bucket}</p>
            <p>Access key: {s.storage.access_key || "Not configured"}</p>
          </>
        )}
        {tab === "security" && (
          <>
            <p>
              Session lifetime: {s.security.session_max_age_hours} hours · Idle
              timeout: {s.security.idle_timeout_hours} hours
            </p>
            <Button variant="danger" onClick={() => setRevoke(true)}>
              Sign out other sessions
            </Button>
            {sessions.isError && <ErrorState error={sessions.error} />}{" "}
            {sessions.data?.map((row) => (
              <div className="border-t pt-3 text-sm" key={row.id}>
                <p>
                  {row.current ? ts("currentSession") : ts("session")} ·{" "}
                  {row.ip_address}
                </p>
                <p className="text-xs text-ink-muted break-all">
                  {row.user_agent}
                </p>
                <p>Last active {dateTime(row.last_seen_at)}</p>
              </div>
            ))}
          </>
        )}
        {tab === "notifications" && (
          <>
            <Field
              label={t("mutedKinds")}
              hint="post.published, post.failed, budget.warning, budget.exceeded, approval.required"
            >
              <Textarea
                aria-label={t("mutedKindsAria")}
                value={muted}
                onChange={(e) => setMuted(e.target.value)}
              />
            </Field>
            <Button
              variant="primary"
              onClick={() =>
                action.mutate(() =>
                  endpoints.updateNotificationPrefs(ws, {
                    muted_kinds: muted
                      .split("\n")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  }),
                )
              }
            >
              Save notification preferences
            </Button>
          </>
        )}
      </Card>
      <ConfirmDialog
        open={revoke}
        onOpenChange={setRevoke}
        title={t("revokeOthers")}
        onConfirm={() => {
          action.mutate(async () => {
            await endpoints.revokeOtherSessions();
            await sessions.refetch();
          });
          setRevoke(false);
        }}
      />
    </div>
  );
}
