import { useEffect, useRef, useState } from "react";
import { useBlocker } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { endpoints, mediaUrl, type Content } from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  SkeletonRows,
} from "@/components/ui/primitives";
import { DateTimePicker, Select, Segmented } from "@/components/ui/forms";
import { ConfirmDialog, Dialog, Tooltip } from "@/components/ui/overlays";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DistributionPanel } from "@/features/distributions/DistributionPanel";
import { useOperation } from "@/hooks/useOperations";
import {
  editorToTelegram,
  telegramToEditor,
  sanitizeTelegramHtml,
  plainText,
  lengthLimit,
} from "@/lib/telegramHtml";
import { rub, dateTime } from "@/lib/format";

export const TRANSFORM_ACTIONS = [
  ["rewrite", "Rewrite"],
  ["shorten", "Shorten"],
  ["expand", "Expand"],
  ["change_tone", "Change tone"],
  ["improve", "Improve"],
  ["generate_headline", "Generate headline"],
  ["regenerate_fragment", "Regenerate fragment"],
  ["generate_cta", "Generate CTA"],
  ["remove_cliches", "Remove AI clichés"],
] as const;

export function ContentDetailPanel({
  workspaceId,
  contentId,
}: {
  workspaceId: string;
  contentId: string;
}) {
  const query = useQuery({
    queryKey: ["content-item", workspaceId, contentId],
    queryFn: () => endpoints.contentDetail(workspaceId, contentId),
    refetchInterval: (q) =>
      q.state.data?.status === "GENERATING" ? 2000 : false,
  });
  return query.isPending ? (
    <SkeletonRows />
  ) : query.isError ? (
    <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  ) : (
    <Studio workspaceId={workspaceId} item={query.data} />
  );
}
function Studio({
  workspaceId: ws,
  item,
}: {
  workspaceId: string;
  item: Content;
}) {
  const [title, setTitle] = useState(item.title),
    [html, setHtml] = useState(item.telegram_html);
  const [target, setTarget] = useState(item.channel_set_id ?? "none"),
    [tone, setTone] = useState(item.tone_profile_id ?? "none");
  const [at, setAt] = useState<string | null>(null),
    [scheduleId, setScheduleId] = useState("none");
  const [preview, setPreview] = useState<"desktop" | "mobile">("desktop"),
    [history, setHistory] = useState(false),
    [viewRevision, setViewRevision] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"delete" | "reject" | null>(null),
    [mediaOpen, setMediaOpen] = useState(false);
  const baseline = useRef(item);
  const dirty =
    title !== baseline.current.title ||
    html !== baseline.current.telegram_html ||
    target !== (baseline.current.channel_set_id ?? "none") ||
    tone !== (baseline.current.tone_profile_id ?? "none");
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const editable = [
    "DRAFT",
    "IDEA",
    "REJECTED",
    "PENDING_APPROVAL",
    "APPROVED",
    "SCHEDULED",
  ].includes(item.status);
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        link: {
          openOnClick: false,
          protocols: ["http", "https", "mailto", "tg"],
        },
      }),
    ],
    content: telegramToEditor(item.telegram_html),
    editable,
    editorProps: {
      attributes: {
        class: "min-h-[220px] p-4 outline-none tg-content",
        "aria-label": "Post body",
      },
    },
    onUpdate: ({ editor }) => setHtml(editorToTelegram(editor.getHTML())),
  });
  useEffect(() => {
    editor?.setEditable(editable);
  }, [editable, editor]);
  useEffect(() => {
    if (!dirtyRef.current) {
      baseline.current = item;
      setTitle(item.title);
      setHtml(item.telegram_html);
      setTarget(item.channel_set_id ?? "none");
      setTone(item.tone_profile_id ?? "none");
      editor?.commands.setContent(telegramToEditor(item.telegram_html), {
        emitUpdate: false,
      });
    }
  }, [item, editor]);
  const blocker = useBlocker({
    shouldBlockFn: () => dirtyRef.current,
    withResolver: true,
    enableBeforeUnload: () => dirtyRef.current,
  });
  const sets = useQuery({
    queryKey: ["channel-sets", ws],
    queryFn: () => endpoints.channelSets(ws),
  });
  const tones = useQuery({
    queryKey: ["tones", ws],
    queryFn: () => endpoints.toneProfiles(ws),
  });
  const settings = useQuery({
    queryKey: ["settings", ws],
    queryFn: () => endpoints.settings(ws),
  });
  const schedules = useQuery({
    queryKey: ["schedules", ws],
    queryFn: () => endpoints.schedules(ws),
  });
  const context = useQuery({
    queryKey: ["context", ws, item.id],
    queryFn: () => endpoints.contentContext(ws, item.id),
  });
  const revisions = useQuery({
    queryKey: ["revisions", ws, item.id],
    queryFn: () => endpoints.revisions(ws, item.id),
    enabled: history,
  });
  const costs = useQuery({
    queryKey: ["content-costs", ws, item.id],
    queryFn: () => endpoints.contentCosts(ws, item.id),
  });
  const imageInfo = useQuery({
    queryKey: ["image-provider", ws],
    queryFn: () => endpoints.imageProvider(ws),
  });
  const media = useQuery({
    queryKey: ["media", ws],
    queryFn: () => endpoints.media(ws),
    enabled: mediaOpen,
  });
  const attached = useQuery({
    queryKey: ["media-detail", ws, item.media_asset_id],
    queryFn: () => endpoints.mediaDetail(ws, item.media_asset_id!),
    enabled: !!item.media_asset_id,
  });
  const action = useOperation(
    ws,
    async (fn: () => Promise<unknown>) => fn(),
    "Updated",
  );
  const save = useOperation(
    ws,
    async () => {
      const updated = await endpoints.editContent(ws, item.id, {
        title,
        telegram_html: html,
        channel_set_id: target === "none" ? null : target,
        tone_profile_id: tone === "none" ? null : tone,
        base_revision_id: baseline.current.latest_revision_id,
      });
      baseline.current = updated;
      setTitle(updated.title);
      setHtml(updated.telegram_html);
    },
    "Changes saved",
  );
  const transform = useOperation(
    ws,
    async (operation: string) => {
      const selection = editor
        ? editor.state.doc.textBetween(
            editor.state.selection.from,
            editor.state.selection.to,
            "\n",
          )
        : "";
      return endpoints.transform(ws, item.id, {
        operation,
        selection,
        tone_profile_id: tone === "none" ? null : tone,
        base_revision_id: item.latest_revision_id,
      });
    },
    "AI action queued",
  );
  const safe = sanitizeTelegramHtml(html),
    count = plainText(safe).length,
    limit = lengthLimit(!!item.media_asset_id);
  const disabled = dirty || action.isPending || transform.isPending;
  return (
    <div className="space-y-4 min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <StatusBadge status={item.status} />
        <span className="text-xs text-ink-muted">
          AI cost {rub(item.ai_cost_rub)} ·{" "}
          {dirty ? "Unsaved changes" : "Saved"}
        </span>
        <Button onClick={() => setHistory(true)}>Version history</Button>
      </div>
      {item.requires_review && (
        <p className="rounded-lg bg-warning/10 p-3 text-warning">
          Manual review required. {item.risk_flags.join(", ")}
        </p>
      )}
      {(item.duplicate_score ?? 0) >= 0.6 && (
        <p className="text-warning">
          Similar to recent content: {Math.round(item.duplicate_score! * 100)}%
        </p>
      )}
      <div className="grid gap-4 2xl:grid-cols-2">
        <Card className="p-4 space-y-3">
          <Field label="Title" htmlFor="post-title">
            <Input
              id="post-title"
              value={title}
              disabled={!editable}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <Select
            ariaLabel="Target channel set"
            value={target}
            onValueChange={setTarget}
            disabled={!editable || item.status === "SCHEDULED"}
            options={[
              { value: "none", label: "No target" },
              ...(sets.data ?? []).map((s) => ({ value: s.id, label: s.name })),
            ]}
          />
          <Select
            ariaLabel="Tone profile"
            value={tone}
            onValueChange={setTone}
            disabled={!editable}
            options={[
              { value: "none", label: "Inherited tone" },
              ...(tones.data ?? []).map((s) => ({
                value: s.id,
                label: s.name,
              })),
            ]}
          />
          <p className="text-xs text-ink-muted">
            Active tone:{" "}
            {context.data?.tone
              ? `${context.data.tone.name} · ${context.data.tone.source}`
              : "Default"}
            {context.data?.series && ` · ${context.data.series.title}`}
          </p>
          <div className="rounded-lg border">
            <div className="flex flex-wrap gap-1 border-b p-2">
              {(
                [
                  "bold",
                  "italic",
                  "underline",
                  "strike",
                  "code",
                  "bulletList",
                  "orderedList",
                  "blockquote",
                  "codeBlock",
                ] as const
              ).map((mark) => (
                <Button
                  key={mark}
                  size="sm"
                  disabled={!editable}
                  aria-pressed={editor?.isActive(mark)}
                  onClick={() => {
                    if (!editor) return;
                    const chain = editor.chain().focus();
                    ({
                      bold: () => chain.toggleBold(),
                      italic: () => chain.toggleItalic(),
                      underline: () => chain.toggleUnderline(),
                      strike: () => chain.toggleStrike(),
                      code: () => chain.toggleCode(),
                      bulletList: () => chain.toggleBulletList(),
                      orderedList: () => chain.toggleOrderedList(),
                      blockquote: () => chain.toggleBlockquote(),
                      codeBlock: () => chain.toggleCodeBlock(),
                    })[mark]()
                      .run();
                  }}
                >
                  {mark}
                </Button>
              ))}
            </div>
            <EditorContent editor={editor} />
          </div>
          <p
            className={
              count > limit ? "text-danger text-xs" : "text-ink-faint text-xs"
            }
          >
            {count} / {limit} characters
          </p>
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={!dirty || !editable || count > limit}
            onClick={() => save.mutate()}
          >
            Save changes
          </Button>
          <div className="flex flex-wrap gap-2">
            {TRANSFORM_ACTIONS.map(([op, label]) => (
              <Button
                key={op}
                size="sm"
                disabled={
                  !editable ||
                  item.status === "SCHEDULED" ||
                  disabled ||
                  (op === "regenerate_fragment" &&
                    editor?.state.selection.empty)
                }
                onClick={() => transform.mutate(op)}
              >
                {label}
              </Button>
            ))}
          </div>
          <p className="text-xs text-ink-faint">
            Save changes before AI actions, approval or scheduling. Select text
            in the editor to regenerate a fragment.
          </p>
        </Card>
        <div className="space-y-3">
          <Segmented
            ariaLabel="Preview size"
            value={preview}
            onChange={setPreview}
            options={[
              { value: "desktop", label: "Desktop" },
              { value: "mobile", label: "Mobile" },
            ]}
          />
          <div
            className={`rounded-xl bg-tg-bg p-4 ${preview === "mobile" ? "max-w-[360px]" : ""}`}
          >
            <div className="rounded-lg bg-tg-bubble p-3">
              <p className="mb-3 text-tg-link text-sm font-semibold">
                {sets.data?.find((s) => s.id === target)?.name ||
                  "Channel preview"}
              </p>
              {attached.data && (
                <img
                  className="mb-3 w-full rounded-lg"
                  src={mediaUrl(attached.data.url)}
                  alt="Post image"
                />
              )}
              <div
                className="tg-content"
                dangerouslySetInnerHTML={{ __html: safe }}
              />
              <div className="mt-2 text-right text-xs text-tg-meta">
                12:00 ✓✓
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={!editable || dirty}
              onClick={() => setMediaOpen(true)}
            >
              Attach image
            </Button>
            {item.media_asset_id && (
              <Button
                disabled={!editable || dirty}
                onClick={() =>
                  action.mutate(() =>
                    endpoints.editContent(ws, item.id, { clear_media: true }),
                  )
                }
              >
                Remove image
              </Button>
            )}
            <Tooltip
              content={
                imageInfo.data?.message || "Generate an image from this post"
              }
            >
              <span>
                <Button
                  disabled={!imageInfo.data?.available || !editable || disabled}
                  onClick={() =>
                    action.mutate(() =>
                      endpoints.generateImage(
                        ws,
                        item.image_prompt || title,
                        item.id,
                      ),
                    )
                  }
                >
                  Generate image
                </Button>
              </span>
            </Tooltip>
          </div>
          {costs.data && (
            <Card className="p-4 text-xs space-y-2">
              {costs.data.lines.map((line) => (
                <div
                  key={line.operation}
                  className="flex justify-between gap-3"
                >
                  <span>
                    {line.operation.replaceAll("_", " ")} · {line.prompt_tokens}{" "}
                    input / {line.completion_tokens} output
                  </span>
                  <span>{rub(line.cost_rub)}</span>
                </div>
              ))}
              <p>
                Text {rub(costs.data.text_cost_rub)} · Image{" "}
                {rub(costs.data.image_cost_rub)} · Total{" "}
                {rub(costs.data.total_rub)}
              </p>
            </Card>
          )}
        </div>
      </div>
      <Card className="p-4 flex flex-wrap items-center gap-2">
        {item.status === "DRAFT" && (
          <Button
            disabled={disabled}
            onClick={() =>
              action.mutate(() => endpoints.submitContent(ws, item.id))
            }
          >
            Submit for approval
          </Button>
        )}
        {item.status === "PENDING_APPROVAL" && (
          <>
            <Button
              variant="primary"
              disabled={disabled}
              onClick={() =>
                action.mutate(() => endpoints.approveContent(ws, item.id))
              }
            >
              Approve
            </Button>
            <Button
              variant="danger"
              disabled={disabled}
              onClick={() => setConfirm("reject")}
            >
              Reject
            </Button>
          </>
        )}
        {item.status === "APPROVED" && (
          <>
            <div className="w-64">
              <DateTimePicker
                value={at}
                onChange={setAt}
                timeZone={settings.data?.general.timezone ?? "UTC"}
              />
            </div>
            <Button
              disabled={disabled || !at}
              onClick={() =>
                action.mutate(() =>
                  endpoints.scheduleContent(ws, item.id, { scheduled_at: at! }),
                )
              }
            >
              Schedule
            </Button>
            <div className="w-52">
              <Select
                ariaLabel="Schedule rule"
                value={scheduleId}
                onValueChange={setScheduleId}
                options={[
                  { value: "none", label: "Choose schedule rule" },
                  ...(schedules.data ?? [])
                    .filter((s) => s.enabled)
                    .map((s) => ({ value: s.id, label: s.name })),
                ]}
              />
            </div>
            <Button
              disabled={disabled || scheduleId === "none"}
              onClick={() =>
                action.mutate(() =>
                  endpoints.scheduleContent(ws, item.id, {
                    schedule_id: scheduleId,
                  }),
                )
              }
            >
              Next free slot
            </Button>
            <Button
              disabled={disabled}
              onClick={() =>
                action.mutate(() => endpoints.publishNow(ws, item.id))
              }
            >
              Publish now
            </Button>
          </>
        )}
        {item.status === "SCHEDULED" && (
          <>
            <span>
              {dateTime(item.scheduled_at, settings.data?.general.timezone)}
            </span>
            <Button
              disabled={disabled}
              onClick={() =>
                action.mutate(() => endpoints.unscheduleContent(ws, item.id))
              }
            >
              Unschedule
            </Button>
          </>
        )}
        {!["PUBLISHING", "GENERATING", "ARCHIVED"].includes(item.status) && (
          <Button
            disabled={disabled}
            onClick={() =>
              action.mutate(() => endpoints.archiveContent(ws, item.id))
            }
          >
            Archive
          </Button>
        )}
        {!["PUBLISHING", "PUBLISHED", "PARTIALLY_PUBLISHED"].includes(
          item.status,
        ) && (
          <Button
            variant="danger"
            disabled={disabled}
            onClick={() => setConfirm("delete")}
          >
            Delete
          </Button>
        )}
      </Card>
      <DistributionPanel workspaceId={ws} contentId={item.id} />
      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={confirm === "reject" ? "Reject this post?" : "Delete this post?"}
        destructive
        onConfirm={() => {
          action.mutate(() =>
            confirm === "reject"
              ? endpoints.rejectContent(ws, item.id)
              : endpoints.deleteContent(ws, item.id),
          );
          setConfirm(null);
        }}
      />
      <ConfirmDialog
        open={blocker.status === "blocked"}
        onOpenChange={(open) => !open && blocker.reset?.()}
        title="Discard unsaved changes?"
        description="Your changes have not been saved."
        confirmLabel="Discard and leave"
        destructive
        onConfirm={() => blocker.proceed?.()}
      />
      <Dialog
        open={history}
        onOpenChange={setHistory}
        title="Version history"
        size="lg"
      >
        {revisions.isPending ? (
          <SkeletonRows />
        ) : revisions.isError ? (
          <ErrorState error={revisions.error} />
        ) : (
          revisions.data?.map((r) => (
            <div key={r.id} className="border-b py-3 space-y-2">
              <div className="flex flex-wrap justify-between gap-2">
                <span>
                  v{r.version} · {r.action} · {r.author_name} ·{" "}
                  {dateTime(r.created_at)} · {r.is_ai ? "AI" : "Manual"} ·{" "}
                  {rub(r.cost_rub)}
                </span>
                <Button
                  size="sm"
                  onClick={() =>
                    setViewRevision(viewRevision === r.id ? null : r.id)
                  }
                >
                  View
                </Button>
                <Button
                  size="sm"
                  disabled={
                    disabled || !editable || item.status === "SCHEDULED"
                  }
                  onClick={() =>
                    action.mutate(() =>
                      endpoints.restoreRevision(ws, item.id, r.id),
                    )
                  }
                >
                  Restore
                </Button>
              </div>
              {viewRevision === r.id && (
                <>
                  <div
                    className="tg-content"
                    dangerouslySetInnerHTML={{
                      __html: sanitizeTelegramHtml(r.telegram_html),
                    }}
                  />
                  <p>
                    {r.diff.map((d, i) => (
                      <span
                        key={i}
                        className={
                          d.op === "delete"
                            ? "bg-danger/20 line-through"
                            : d.op === "insert"
                              ? "bg-success/20"
                              : ""
                        }
                      >
                        {d.text}{" "}
                      </span>
                    ))}
                  </p>
                </>
              )}
            </div>
          ))
        )}
      </Dialog>
      <Dialog
        open={mediaOpen}
        onOpenChange={setMediaOpen}
        title="Choose an image"
      >
        <div className="grid grid-cols-3 gap-2">
          {media.data?.items.map((a) => (
            <button
              key={a.id}
              onClick={() => {
                action.mutate(() =>
                  endpoints.editContent(ws, item.id, { media_asset_id: a.id }),
                );
                setMediaOpen(false);
              }}
            >
              <img
                src={mediaUrl(a.url)}
                alt={a.original_filename || "Gallery image"}
                className="aspect-square object-cover rounded-lg"
              />
            </button>
          ))}
        </div>
        {!media.data?.items.length && (
          <EmptyState
            title="No images"
            description="Upload images in the Media Gallery."
          />
        )}
      </Dialog>
    </div>
  );
}
