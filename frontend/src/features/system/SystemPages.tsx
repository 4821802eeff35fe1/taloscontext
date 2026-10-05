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
} from "@/components/ui/primitives";
import { Checkbox, Select, Tabs } from "@/components/ui/forms";
import { ConfirmDialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";
import { useLanguage } from "@/hooks/useLanguage";
import { SUPPORTED_LANGUAGES, type Language } from "@/i18n";
import {
  auditActionLabel,
  ctaKeyLabel,
  entityLabel,
  misfirePolicyLabel,
  notificationText,
  roleLabel,
  statusLabel,
} from "@/i18n/labels";
import { dateTime, rub, timezoneOptions } from "@/lib/format";

const AUDIT_ENTITIES = [
  "content",
  "workspace",
  "publication",
  "job",
  "telegram_account",
  "channel_set",
  "channel",
  "source",
  "schedule",
  "series",
  "knowledge_base",
  "knowledge_document",
  "tone_profile",
  "media",
];

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
          aria-label={t("audit.search")}
          placeholder={t("audit.searchPlaceholder")}
          className="w-full sm:max-w-xs"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select
          className="w-full sm:w-60"
          ariaLabel={t("audit.action")}
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
          className="w-full sm:w-52"
          ariaLabel={t("audit.actor")}
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
          className="w-full sm:w-52"
          ariaLabel={t("audit.entity")}
          value={entity}
          onValueChange={setEntity}
          options={["all", ...AUDIT_ENTITIES].map((value) => ({
            value,
            label: value === "all" ? t("audit.allEntities") : entityLabel(value),
          }))}
        />
        <Input
          aria-label={t("audit.from")}
          placeholder={t("audit.fromPlaceholder")}
          className="w-full sm:w-44"
          value={since}
          onChange={(e) => setSince(e.target.value)}
        />
        <Input
          aria-label={t("audit.until")}
          placeholder={t("audit.untilPlaceholder")}
          className="w-full sm:w-44"
          value={until}
          onChange={(e) => setUntil(e.target.value)}
        />
      </div>
      <Card>
        {query.isPending ? (
          <SkeletonRows />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !query.data.pages[0].items.length ? (
          <EmptyState title={t("audit.empty")} />
        ) : (
          query.data.pages
            .flatMap((p) => p.items)
            .map((e) => (
              <details key={e.id} className="border-b p-4">
                <summary className="flex cursor-pointer flex-wrap justify-between gap-2">
                  <span className="min-w-0 break-words">
                    {e.actor_name || t("audit.system")} · {auditActionLabel(e.action)}
                  </span>
                  <span className="text-xs text-ink-muted">
                    {dateTime(e.created_at)}
                  </span>
                </summary>
                <p className="mt-2 break-all text-xs text-ink-faint">
                  {e.entity_type ? entityLabel(e.entity_type) : "—"}
                  {e.entity_id && " · " + e.entity_id}
                  {" · "}
                  <span className="font-mono">{e.action}</span>
                </p>
                <pre className="mt-2 overflow-auto text-xs">
                  {JSON.stringify(e.metadata, null, 2)}
                </pre>
              </details>
            ))
        )}
        {query.hasNextPage && (
          <Button className="m-4" onClick={() => void query.fetchNextPage()}>
            {t("common:action.loadMore")}
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
            {t("notifications.markAllRead")}
          </Button>
        }
      />
      <Select
        className="w-full sm:w-44"
        ariaLabel={t("notifications.filter")}
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
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !query.data.items.length ? (
          <EmptyState title={t("notifications.empty")} />
        ) : (
          query.data.items.map((n) => (
            <div
              key={n.id}
              className={`flex flex-wrap justify-between gap-3 border-b p-4 ${n.read ? "" : "bg-accent/5"}`}
            >
              <div className="min-w-0 flex-1">
                <p className="break-words">
                  {!n.read && (
                    <span aria-label={t("notifications.unreadMark")}>● </span>
                  )}
                  {notificationText(n)}
                </p>
                <p className="mt-1 text-xs text-ink-faint">
                  {t(`notifications.kind.${n.kind.replaceAll(".", "_")}`, { defaultValue: n.kind })} ·{" "}
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
                  {t("notifications.markRead")}
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
  if (query.isError)
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  return <SettingsEditor key={ws} ws={ws} settings={query.data} />;
}

/** Notification kinds a user can mute; labels come from system:notifications.kind. */
const NOTIFICATION_KINDS = [
  "post.published",
  "post.partially_published",
  "post.failed",
  "approval.required",
  "budget.warning",
  "budget.exceeded",
  "telegram.flood_wait",
  "telegram.disconnected",
  "schedule.misfired",
  "ai.failed",
];

const ROLES: Role[] = ["OWNER", "ADMIN", "EDITOR", "APPROVER", "VIEWER"];

function LanguageSetting() {
  const { t } = useTranslation("settings");
  const { language, setLanguage, saving } = useLanguage();
  return (
    <Field
      label={t("general.language")}
      hint={t("general.languageHint")}
      htmlFor="settings-language"
    >
      <Select
        id="settings-language"
        ariaLabel={t("general.language")}
        className="w-full sm:w-60"
        disabled={saving}
        value={language}
        onValueChange={(v) => setLanguage(v as Language)}
        options={SUPPORTED_LANGUAGES.map((lang) => ({
          value: lang,
          label: t(`common:language.name.${lang}`),
        }))}
      />
    </Field>
  );
}

function SettingsEditor({
  ws,
  settings: s,
}: {
  ws: string;
  settings: Settings;
}) {
  const { t } = useTranslation("settings");
  const [tab, setTab] = useState("general"),
    [general, setGeneral] = useState(s.general),
    [budget, setBudget] = useState(s.budget),
    [muted, setMuted] = useState<string[]>(s.notifications.muted_kinds ?? []),
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
  const configured = (value: string | null) =>
    value || t("common:state.notConfigured");
  const yesNo = (v: boolean) => (v ? t("common:state.yes") : t("common:state.no"));
  // Kinds muted earlier that aren't in the list stay muted.
  const kinds = [...NOTIFICATION_KINDS, ...muted.filter((k) => !NOTIFICATION_KINDS.includes(k))];
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
          label: t(`tab.${value}`),
        }))}
      />
      <Card className="max-w-3xl space-y-4 p-5">
        {tab === "general" && (
          <>
            <h2 className="font-medium">{t("general.personal")}</h2>
            <LanguageSetting />
            <h2 className="pt-4 font-medium">{t("general.workspace")}</h2>
            <Field label={t("general.workspaceName")} htmlFor="settings-workspace-name">
              <Input
                id="settings-workspace-name"
                value={general.workspace_name}
                onChange={(e) =>
                  setGeneral({ ...general, workspace_name: e.target.value })
                }
              />
            </Field>
            <Field label={t("general.timezone")} htmlFor="settings-timezone">
              <Select
                id="settings-timezone"
                ariaLabel={t("general.timezone")}
                value={general.timezone}
                onValueChange={(timezone) => setGeneral({ ...general, timezone })}
                options={timezoneOptions(general.timezone)}
              />
            </Field>
            <Field label={t("general.misfirePolicy")} htmlFor="settings-misfire">
              <Select
                id="settings-misfire"
                ariaLabel={t("general.misfirePolicy")}
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
            </Field>
            <Field label={t("general.misfireGrace")} htmlFor="settings-grace">
              <Input
                id="settings-grace"
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
              <Field key={k} label={t("general.cta", { key: ctaKeyLabel(k) })} htmlFor={`settings-cta-${k}`}>
                <Input
                  id={`settings-cta-${k}`}
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
              {t("general.save")}
            </Button>
            <h2 className="pt-4 font-medium">{t("members.title")}</h2>
            {members.data?.map((m) => (
              <div
                key={m.user_id}
                className="flex flex-wrap items-center gap-2"
              >
                <span className="min-w-0 flex-1 break-words">{m.full_name || m.email}</span>
                <Select
                  ariaLabel={t("members.roleFor", { email: m.email })}
                  value={m.role}
                  onValueChange={(v) =>
                    action.mutate(() =>
                      endpoints.changeRole(ws, m.user_id, v as Role),
                    )
                  }
                  className="w-full sm:w-44"
                  options={ROLES.map((value) => ({ value, label: roleLabel(value) }))}
                />
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              <Input
                aria-label={t("members.email")}
                className="w-full sm:max-w-xs"
                type="email"
                placeholder={t("members.emailPlaceholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Select
                ariaLabel={t("members.newRole")}
                value={role}
                onValueChange={(v) => setRole(v as Role)}
                className="w-full sm:w-44"
                options={ROLES.filter((r) => r !== "OWNER").map((value) => ({
                  value,
                  label: roleLabel(value),
                }))}
              />
              <Button
                disabled={!email}
                onClick={() =>
                  action.mutate(() => endpoints.addMember(ws, email, role))
                }
              >
                {t("members.add")}
              </Button>
            </div>
          </>
        )}
        {tab === "budget" && (
          <>
            {(Object.keys(budget) as (keyof typeof budget)[]).map((k) => (
              <Field label={t(`budget.${k}`)} key={k} htmlFor={`settings-${k}`}>
                <Input
                  id={`settings-${k}`}
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
              {t("budget.save")}
            </Button>
          </>
        )}
        {tab === "ai" && (
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
            <dt className="text-ink-muted">{t("ai.textProvider")}</dt>
            <dd>{s.ai.text_provider}</dd>
            <dt className="text-ink-muted">{t("ai.baseUrl")}</dt>
            <dd className="break-all">{s.ai.agent_base_url || "—"}</dd>
            <dt className="text-ink-muted">{t("ai.apiKey")}</dt>
            <dd className="break-all">{configured(s.ai.agent_api_key)}</dd>
            <dt className="text-ink-muted">{t("ai.model")}</dt>
            <dd>{s.ai.model}</dd>
            <dt className="text-ink-muted">{t("ai.imageProvider")}</dt>
            <dd>
              {s.ai.image_provider} · {statusLabel(s.ai.image_provider_status, "provider")}
            </dd>
            <dt className="text-ink-muted">{t("ai.gatewayKey")}</dt>
            <dd className="break-all">{configured(s.ai.gateway_api_key)}</dd>
            {Object.entries(s.ai.pricing).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-ink-muted">{t(`ai.pricing.${k}`, { defaultValue: k })}</dt>
                <dd>{t("ai.perMillion", { price: rub(v) })}</dd>
              </div>
            ))}
          </dl>
        )}
        {tab === "telegram" && (
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
            {Object.entries(s.telegram).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-ink-muted">{t(`telegram.${k}`, { defaultValue: k })}</dt>
                <dd>{yesNo(v)}</dd>
              </div>
            ))}
          </dl>
        )}
        {tab === "storage" && (
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
            <dt className="text-ink-muted">{t("storage.endpoint")}</dt>
            <dd className="break-all">{s.storage.endpoint_host}</dd>
            <dt className="text-ink-muted">{t("storage.bucket")}</dt>
            <dd className="break-all">{s.storage.bucket}</dd>
            <dt className="text-ink-muted">{t("storage.accessKey")}</dt>
            <dd className="break-all">{configured(s.storage.access_key)}</dd>
          </dl>
        )}
        {tab === "security" && (
          <>
            <p>
              {t("security.lifetime", { count: s.security.session_max_age_hours })} ·{" "}
              {t("security.idle", { count: s.security.idle_timeout_hours })}
            </p>
            <Button variant="danger" onClick={() => setRevoke(true)}>
              {t("security.revokeOthers")}
            </Button>
            {sessions.isError && <ErrorState error={sessions.error} />}
            {sessions.data?.map((row) => (
              <div className="border-t pt-3 text-sm" key={row.id}>
                <p>
                  {row.current ? t("security.current") : t("security.session")} ·{" "}
                  {row.ip_address}
                </p>
                <p className="break-all text-xs text-ink-muted">
                  {row.user_agent}
                </p>
                <p>{t("security.lastActive", { time: dateTime(row.last_seen_at) })}</p>
              </div>
            ))}
          </>
        )}
        {tab === "notifications" && (
          <>
            <fieldset className="space-y-2">
              <legend className="label">{t("notifications.muted")}</legend>
              <p className="text-xs text-ink-muted">{t("notifications.mutedHint")}</p>
              {kinds.map((kind) => (
                <label key={kind} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    label={t(`system:notifications.kind.${kind.replaceAll(".", "_")}`, { defaultValue: kind })}
                    checked={muted.includes(kind)}
                    onCheckedChange={(v) =>
                      setMuted(v ? [...muted, kind] : muted.filter((k) => k !== kind))
                    }
                  />
                  {t(`system:notifications.kind.${kind.replaceAll(".", "_")}`, { defaultValue: kind })}
                </label>
              ))}
            </fieldset>
            <Button
              variant="primary"
              onClick={() =>
                action.mutate(() =>
                  endpoints.updateNotificationPrefs(ws, { muted_kinds: muted }),
                )
              }
            >
              {t("notifications.save")}
            </Button>
          </>
        )}
      </Card>
      <ConfirmDialog
        open={revoke}
        onOpenChange={setRevoke}
        title={t("security.revokeConfirm")}
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
