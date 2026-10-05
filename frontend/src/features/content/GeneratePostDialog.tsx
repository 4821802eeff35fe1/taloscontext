import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, errorText } from "@/lib/api";
import { Dialog } from "@/components/ui/Dialog";
import { Select } from "@/components/ui/Select";

export function GeneratePostDialog({
  workspaceId,
  open,
  onOpenChange,
  onCreated,
}: {
  workspaceId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: (contentId: string) => void;
}) {
  const { t } = useTranslation("content");
  const client = useQueryClient();
  const [instruction, setInstruction] = useState("");
  const [channelSetId, setChannelSetId] = useState<string | undefined>(
    undefined,
  );
  const [error, setError] = useState<string | null>(null);

  const channelSets = useQuery({
    queryKey: ["channel-sets", workspaceId],
    queryFn: () => endpoints.channelSets(workspaceId),
  });

  const generate = useMutation({
    mutationFn: () =>
      endpoints.generateContent(workspaceId, {
        instruction,
        channel_set_id: channelSetId ?? null,
      }),
    onSuccess: ({ content: item }) => {
      client.invalidateQueries({ queryKey: ["content", workspaceId] });
      onOpenChange(false);
      setInstruction("");
      onCreated(item.id);
    },
    onError: (e) => setError(errorText(e)),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("generate.title")}
      description={t("generate.description")}
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          generate.mutate();
        }}
      >
        <div>
          <label className="label" htmlFor="generation-instruction">
            {t("generate.instruction")}
          </label>
          <textarea
            id="generation-instruction"
            className="input min-h-[90px]"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder={t("generate.instructionPlaceholder")}
            required
          />
        </div>
        <div>
          <label className="label">{t("generate.target")}</label>
          <Select
            value={channelSetId}
            onValueChange={setChannelSetId}
            placeholder={t("generate.chooseLater")}
            options={(channelSets.data ?? []).map((s) => ({
              value: s.id,
              label: s.name,
            }))}
          />
        </div>
        {error && <p className="text-sm text-danger">{error}</p>}
        <button className="btn-primary w-full" disabled={generate.isPending}>
          {generate.isPending ? t("generate.generating") : t("generate.submit")}
        </button>
      </form>
    </Dialog>
  );
}
