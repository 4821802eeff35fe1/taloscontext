import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";

const MODE_OPTIONS = [
  { value: "MANUAL", label: "Manual — nothing is created automatically" },
  { value: "APPROVAL", label: "Approval — AI drafts land in the approval queue" },
  { value: "AUTOPILOT", label: "Autopilot — AI drafts, approves, and schedules" },
];

export function AutopilotPage({ workspaceId }: { workspaceId: string }) {
  const client = useQueryClient();
  const { data: config } = useQuery({ queryKey: ["autopilot", workspaceId], queryFn: () => endpoints.autopilot(workspaceId) });
  const channelSets = useQuery({ queryKey: ["channel-sets", workspaceId], queryFn: () => endpoints.channelSets(workspaceId) });

  const [mode, setMode] = useState("MANUAL");
  const [channelSetId, setChannelSetId] = useState<string | undefined>(undefined);
  const [postsPerDay, setPostsPerDay] = useState(1);
  const [dailyBudget, setDailyBudget] = useState("50");
  const [monthlyBudget, setMonthlyBudget] = useState("1500");
  const [maxPostCost, setMaxPostCost] = useState("15");

  useEffect(() => {
    if (config) {
      setMode(config.mode);
      setChannelSetId(config.channel_set_id ?? undefined);
      setPostsPerDay(config.posts_per_day);
      setDailyBudget(config.daily_budget_rub);
      setMonthlyBudget(config.monthly_budget_rub);
      setMaxPostCost(config.max_cost_per_post_rub);
    }
  }, [config]);

  const save = useMutation({
    mutationFn: () =>
      endpoints.updateAutopilot(workspaceId, {
        mode,
        channel_set_id: channelSetId ?? null,
        posts_per_day: postsPerDay,
        daily_budget_rub: dailyBudget,
        monthly_budget_rub: monthlyBudget,
        max_cost_per_post_rub: maxPostCost,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["autopilot", workspaceId] }),
  });

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-xl font-semibold text-ink">Autopilot</h1>

      <Card className="space-y-4">
        <div>
          <label className="label">Mode</label>
          <Select value={mode} onValueChange={setMode} options={MODE_OPTIONS} />
        </div>
        <div>
          <label className="label">Target channel set</label>
          <Select
            value={channelSetId}
            onValueChange={setChannelSetId}
            placeholder="Choose a channel set"
            options={(channelSets.data ?? []).map((s) => ({ value: s.id, label: s.name }))}
          />
        </div>
        <div>
          <label className="label">Posts per day</label>
          <input
            type="number"
            min={1}
            max={20}
            className="input"
            value={postsPerDay}
            onChange={(e) => setPostsPerDay(parseInt(e.target.value, 10))}
          />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="label">Daily budget (₽)</label>
            <input className="input" value={dailyBudget} onChange={(e) => setDailyBudget(e.target.value)} />
          </div>
          <div>
            <label className="label">Monthly budget (₽)</label>
            <input className="input" value={monthlyBudget} onChange={(e) => setMonthlyBudget(e.target.value)} />
          </div>
          <div>
            <label className="label">Max per post (₽)</label>
            <input className="input" value={maxPostCost} onChange={(e) => setMaxPostCost(e.target.value)} />
          </div>
        </div>
        <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
          Save settings
        </button>
      </Card>
    </div>
  );
}
