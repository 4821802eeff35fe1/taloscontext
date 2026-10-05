import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, type Source } from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  SkeletonRows,
  Field,
} from "@/components/ui/primitives";
import { Select, Switch, TagInput } from "@/components/ui/forms";
import { Dialog, ConfirmDialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";
import { dateTime } from "@/lib/format";
export function SourcesPage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("ai");
  const [editing, setEditing] = useState<Source | null | undefined>(),
    [remove, setRemove] = useState<string | null>(null);
  const query = useQuery({
      queryKey: ["sources", ws],
      queryFn: () => endpoints.sources(ws),
    }),
    action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader
        title={t("sources.title")}
        description={t("sources.description")}
        actions={
          <Button variant="primary" onClick={() => setEditing(null)}>
            Add source
          </Button>
        }
      />
      {query.isPending ? (
        <SkeletonRows />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.length ? (
        <EmptyState
          title={t("sources.emptyTitle")}
          description={t("sources.emptyDescription")}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {query.data.map((s) => (
            <Card key={s.id} className="p-4 space-y-3">
              <div className="flex justify-between">
                <h2>{s.name}</h2>
                <Switch
                  label={`Enable ${s.name}`}
                  checked={s.enabled}
                  onCheckedChange={(enabled) =>
                    action.mutate(() =>
                      endpoints.updateSource(ws, s.id, { enabled }),
                    )
                  }
                />
              </div>
              <p className="text-xs text-ink-muted">
                {s.kind} · {s.items_new} new / {s.items_total} total · Every{" "}
                {String(s.config.fetch_interval_minutes)} min
              </p>
              <p className="text-xs">
                Last fetch: {dateTime(s.last_fetched_at)} · Success:{" "}
                {dateTime(s.last_success_at)}
              </p>
              {s.last_error && (
                <p className="text-xs text-danger">{s.last_error}</p>
              )}
              <div className="flex gap-2">
                <Button
                  onClick={() =>
                    action.mutate(() => endpoints.fetchSource(ws, s.id))
                  }
                >
                  Fetch now
                </Button>
                <Button onClick={() => setEditing(s)}>{t("sources.edit")}</Button>
                <Button variant="danger" onClick={() => setRemove(s.id)}>
                  Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing !== undefined && (
        <SourceEditor
          ws={ws}
          source={editing}
          onClose={() => setEditing(undefined)}
        />
      )}
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(o) => !o && setRemove(null)}
        title={t("sources.deleteTitle")}
        destructive
        onConfirm={() => {
          action.mutate(() => endpoints.deleteSource(ws, remove!));
          setRemove(null);
        }}
      />
    </div>
  );
}
function SourceEditor({
  ws,
  source,
  onClose,
}: {
  ws: string;
  source: Source | null;
  onClose: () => void;
}) {
  const [name, setName] = useState(source?.name ?? ""),
    [kind, setKind] = useState(source?.kind ?? "rss"),
    [url, setUrl] = useState(String(source?.config.url ?? "")),
    [channel, setChannel] = useState(String(source?.config.channel ?? "")),
    [account, setAccount] = useState(
      String(source?.config.account_id ?? "none"),
    ),
    [interval, setInterval] = useState(
      Number(source?.config.fetch_interval_minutes ?? 60),
    ),
    [keywords, setKeywords] = useState<string[]>(
      (source?.config.keywords as string[]) ?? [],
    );
  const accounts = useQuery({
    queryKey: ["telegram-accounts", ws],
    queryFn: () => endpoints.telegramAccounts(ws),
  });
  const action = useOperation(ws, async () => {
    const body = {
      name,
      kind,
      enabled: source?.enabled ?? true,
      config: {
        url: kind === "telegram" ? null : url,
        channel: kind === "telegram" ? channel : null,
        account_id: kind === "telegram" ? account : null,
        fetch_interval_minutes: interval,
        keywords,
        category: "news",
      },
    };
    if (source) await endpoints.updateSource(ws, source.id, body);
    else await endpoints.createSource(ws, body);
    onClose();
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={t("sources.dialogTitle")}>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate();
        }}
      >
        <Input
          aria-label={t("sources.sourceNameAria")}
          placeholder={t("sources.namePlaceholder")}
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Select
          ariaLabel="Source type"
          disabled={!!source}
          value={kind}
          onValueChange={setKind}
          options={["rss", "url", "manual", "telegram"].map((value) => ({
            value,
            label: value,
          }))}
        />
        {kind === "telegram" ? (
          <>
            <Input
              aria-label={t("sources.telegramChannelAria")}
              placeholder="@channel"
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
            />
            <Select
              ariaLabel="Source Telegram account"
              value={account}
              onValueChange={setAccount}
              options={(accounts.data ?? [])
                .filter((a) => a.status === "CONNECTED")
                .map((a) => ({ value: a.id, label: a.phone_masked }))}
            />
          </>
        ) : (
          <Input
            aria-label={t("sources.sourceUrlAria")}
            type="url"
            placeholder="https://…"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        )}
        <Field label={t("sources.fetchInterval")}>
          <Input
            aria-label={t("sources.fetchIntervalAria")}
            type="number"
            min={10}
            value={interval}
            onChange={(e) => setInterval(Number(e.target.value))}
          />
        </Field>
        <TagInput
          ariaLabel="Keywords"
          value={keywords}
          onChange={setKeywords}
        />
        <Button type="submit" loading={action.isPending} variant="primary">
          Save source
        </Button>
      </form>
    </Dialog>
  );
}
export function IdeasPage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("ai");
  const [status, setStatus] = useState("NEW"),
    [q, setQ] = useState("");
  const query = useQuery({
    queryKey: ["ideas", ws, status, q],
    queryFn: () =>
      endpoints.ideas(ws, {
        status: status === "all" ? undefined : [status],
        q,
      }),
  });
  const action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader
        title={t("ideas.title")}
        description={t("ideas.description")}
      />
      <div className="flex gap-2 flex-wrap">
        <Select
          ariaLabel={t("ideas.statusAria")}
          className="w-52"
          value={status}
          onValueChange={setStatus}
          options={["all", "NEW", "SHORTLISTED", "USED", "DISMISSED"].map(
            (value) => ({
              value,
              label: value === "all" ? "All ideas" : value,
            }),
          )}
        />
        <Input
          aria-label={t("ideas.searchAria")}
          placeholder={t("ideas.search")}
          className="max-w-xs"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      {query.isPending ? (
        <SkeletonRows />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.items.length ? (
        <EmptyState
          title={t("ideas.emptyTitle")}
          description={t("ideas.emptyDescription")}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {query.data.items.map((i) => (
            <Card key={i.id} className="p-4 space-y-3">
              <h2 className="font-medium">{i.title}</h2>
              <p className="text-xs text-ink-faint">
                {i.source_name} · {dateTime(i.published_at)} · {i.status}
              </p>
              <p className="text-sm text-ink-muted">{i.summary}</p>
              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() =>
                    action.mutate(() =>
                      endpoints.generateContent(ws, { source_item_id: i.id }),
                    )
                  }
                >
                  Generate post
                </Button>
                <Button
                  onClick={() =>
                    action.mutate(() =>
                      endpoints.updateIdea(ws, i.id, "SHORTLISTED"),
                    )
                  }
                >
                  Save
                </Button>
                <Button
                  onClick={() =>
                    action.mutate(() =>
                      endpoints.updateIdea(ws, i.id, "DISMISSED"),
                    )
                  }
                >
                  Dismiss
                </Button>
                {/^https?:\/\//i.test(i.url) && (
                  <a
                    className="btn-secondary"
                    href={i.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open source
                  </a>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
