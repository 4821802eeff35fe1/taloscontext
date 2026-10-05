import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, type ToneInput, type ToneProfile } from "@/lib/api";
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
import { TagInput } from "@/components/ui/forms";
import { ConfirmDialog, Dialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";
// Defaults below are prompt inputs (content settings), not UI copy.
const initial: ToneInput = {
  name: "",
  description: "",
  language: "Russian",
  addressing: "вы",
  formality: "conversational",
  emoji_policy: "minimal",
  headline_style: "clear",
  paragraph_style: "short",
  average_length: "800–1200 characters",
  cta_style: "direct",
  allowed_vocabulary: [],
  forbidden_vocabulary: [],
  cliches_blacklist: [],
  good_examples: [],
  bad_examples: [],
};
export function TonePage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("ai");
  const [editing, setEditing] = useState<ToneProfile | null | undefined>(),
    [remove, setRemove] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["tones", ws],
    queryFn: () => endpoints.toneProfiles(ws),
  });
  const action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader
        title={t("tone.title")}
        description={t("tone.description")}
        actions={
          <Button variant="primary" onClick={() => setEditing(null)}>
            {t("tone.create")}
          </Button>
        }
      />
      {query.isPending ? (
        <SkeletonRows />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.length ? (
        <EmptyState
          title={t("tone.empty.title")}
          description={t("tone.empty.description")}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {query.data.map((p) => (
            <Card key={p.id} className="p-4 space-y-3">
              <h2 className="break-words font-medium">
                {p.name}
                {p.is_workspace_default && " · " + t("tone.workspaceDefault")}
              </h2>
              <p className="text-sm text-ink-muted">{p.description}</p>
              <p className="text-xs">
                {t("common:count.channels", { count: p.channel_count })} ·{" "}
                {t("tone.series", { count: p.series_count })}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => setEditing(p)}>{t("common:action.edit")}</Button>
                <Button
                  disabled={p.is_workspace_default}
                  onClick={() =>
                    action.mutate(() => endpoints.makeToneDefault(ws, p.id))
                  }
                >
                  {t("tone.makeDefault")}
                </Button>
                <Button variant="danger" onClick={() => setRemove(p.id)}>
                  {t("common:action.delete")}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing !== undefined && (
        <ToneEditor
          key={editing?.id || "new"}
          ws={ws}
          profile={editing}
          onClose={() => setEditing(undefined)}
        />
      )}
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(open) => !open && setRemove(null)}
        title={t("tone.deleteConfirm")}
        destructive
        onConfirm={() => {
          action.mutate(() => endpoints.deleteTone(ws, remove!));
          setRemove(null);
        }}
      />
    </div>
  );
}
function ToneEditor({
  ws,
  profile,
  onClose,
}: {
  ws: string;
  profile: ToneProfile | null;
  onClose: () => void;
}) {
  const { t } = useTranslation("ai");
  const [draft, setDraft] = useState<ToneInput>(profile ?? initial);
  const action = useOperation(ws, async () => {
    if (profile) await endpoints.updateTone(ws, profile.id, draft);
    else await endpoints.createTone(ws, draft);
    onClose();
  });
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={profile ? t("tone.editTitle") : t("tone.createTitle")}
      size="lg"
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate();
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {(Object.keys(initial) as (keyof ToneInput)[])
            .filter((k) => typeof initial[k] === "string")
            .map((k) => (
              <Field
                key={k}
                label={t(`tone.field.${k}`)}
                htmlFor={`tone-${k}`}
              >
                <Input
                  id={`tone-${k}`}
                  value={draft[k] as string}
                  required={k === "name"}
                  onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
                />
              </Field>
            ))}
        </div>
        {(
          [
            "allowed_vocabulary",
            "forbidden_vocabulary",
            "cliches_blacklist",
          ] as const
        ).map((k) => (
          <Field key={k} label={t(`tone.field.${k}`)}>
            <TagInput
              ariaLabel={t(`tone.field.${k}`)}
              value={draft[k]}
              onChange={(v) => setDraft({ ...draft, [k]: v })}
            />
          </Field>
        ))}
        {(["good_examples", "bad_examples"] as const).map((k) => (
          <Field key={k} label={t("tone.onePerLine", { field: t(`tone.field.${k}`) })}>
            <Textarea
              aria-label={t(`tone.field.${k}`)}
              value={draft[k].join("\n")}
              onChange={(e) =>
                setDraft({ ...draft, [k]: e.target.value.split("\n") })
              }
            />
          </Field>
        ))}
        <Button variant="primary" type="submit" loading={action.isPending}>
          {t("tone.save")}
        </Button>
      </form>
    </Dialog>
  );
}
