import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, type Autopilot } from "@/lib/api";
import {
  Button,
  Card,
  ErrorState,
  Field,
  Input,
  PageHeader,
  SkeletonRows,
} from "@/components/ui/primitives";
import { Select, Switch } from "@/components/ui/forms";
import { Tooltip } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";

export function AutopilotPage({ workspaceId: ws }: { workspaceId: string }) {
  const { t } = useTranslation("automation");
  const query = useQuery({
    queryKey: ["autopilot", ws],
    queryFn: () => endpoints.autopilot(ws),
  });
  return (
    <div className="max-w-2xl space-y-4">
      <PageHeader
        title={t("autopilot.title")}
        description={t("autopilot.description")}
      />
      {query.isPending ? (
        <SkeletonRows />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : (
        <AutopilotEditor key={ws} ws={ws} initial={query.data} />
      )}
    </div>
  );
}
function AutopilotEditor({ ws, initial }: { ws: string; initial: Autopilot }) {
  const { t } = useTranslation("automation");
  const [draft, setDraft] = useState(initial);
  const sets = useQuery({
    queryKey: ["channel-sets", ws],
    queryFn: () => endpoints.channelSets(ws),
  });
  const schedules = useQuery({
    queryKey: ["schedules", ws],
    queryFn: () => endpoints.schedules(ws),
  });
  const image = useQuery({
    queryKey: ["image-provider", ws],
    queryFn: () => endpoints.imageProvider(ws),
  });
  const save = useOperation(
    ws,
    () => endpoints.updateAutopilot(ws, draft),
    "Autopilot settings saved",
  );
  const change = <K extends keyof Autopilot>(key: K, value: Autopilot[K]) =>
    setDraft({ ...draft, [key]: value });
  return (
    <Card className="p-5">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label={t("autopilot.mode")}>
          <Select
            ariaLabel={t("autopilot.modeAria")}
            value={draft.mode}
            onValueChange={(v) => change("mode", v)}
            options={[
              { value: "MANUAL", label: t("autopilot.modeLabel.MANUAL") },
              {
                value: "APPROVAL",
                label: t("autopilot.modeLabel.APPROVAL"),
              },
              {
                value: "AUTOPILOT",
                label: t("autopilot.modeLabel.AUTOPILOT"),
              },
            ]}
          />
        </Field>
        <Field label={t("autopilot.target")}>
          <Select
            ariaLabel="Autopilot target"
            value={draft.channel_set_id ?? "none"}
            onValueChange={(v) =>
              change("channel_set_id", v === "none" ? null : v)
            }
            options={[
              { value: "none", label: t("autopilot.chooseChannelSet") },
              ...(sets.data ?? []).map((s) => ({ value: s.id, label: s.name })),
            ]}
          />
        </Field>
        <Field label={t("autopilot.schedule")}>
          <Select
            ariaLabel="Autopilot schedule"
            value={draft.schedule_id ?? "none"}
            onValueChange={(v) =>
              change("schedule_id", v === "none" ? null : v)
            }
            options={[
              { value: "none", label: t("autopilot.noSchedule") },
              ...(schedules.data ?? []).map((s) => ({
                value: s.id,
                label: `${s.name}${s.enabled ? "" : t("autopilot.pausedSuffix")}`,
              })),
            ]}
          />
        </Field>
        <Field label={t("autopilot.postsPerDay")} htmlFor="autopilot-posts">
          <Input
            id="autopilot-posts"
            type="number"
            min={1}
            max={50}
            value={draft.posts_per_day}
            onChange={(e) => change("posts_per_day", Number(e.target.value))}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-3">
          {(
            [
              "daily_budget_rub",
              "monthly_budget_rub",
              "max_cost_per_post_rub",
            ] as const
          ).map((key) => (
            <Field key={key} label={key.replaceAll("_", " ")}>
              <Input
                aria-label={key}
                type="number"
                min={0}
                step="0.01"
                value={draft[key]}
                onChange={(e) => change(key, e.target.value)}
              />
            </Field>
          ))}
        </div>
        <Tooltip
          content={
            !image.data?.available
              ? image.data?.message || "Image provider is unavailable"
              : undefined
          }
        >
          <span className="inline-flex gap-2 items-center">
            <Switch
              label={t("autopilot.generateImages")}
              checked={draft.generate_image}
              disabled={!image.data?.available}
              onCheckedChange={(v) => change("generate_image", v)}
            />
            Generate images
          </span>
        </Tooltip>
        <p className="text-xs text-ink-muted">
          Publishing approved posts continues even when the AI budget is
          exhausted. Missed schedules use your configured misfire policy.
        </p>
        <Button type="submit" variant="primary" loading={save.isPending}>
          Save autopilot
        </Button>
      </form>
    </Card>
  );
}
