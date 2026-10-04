import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { Card, EmptyState } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";

export function JobsPage({ workspaceId }: { workspaceId: string }) {
  const jobs = useQuery({
    queryKey: ["jobs", workspaceId],
    queryFn: () => endpoints.jobs(workspaceId),
    refetchInterval: 5000,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-ink">Jobs</h1>

      <Card className="p-0">
        {jobs.data && jobs.data.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border text-left text-xs text-ink-faint">
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Attempt</th>
                <th className="px-4 py-2 font-medium">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {jobs.data.map((job) => (
                <tr key={job.id}>
                  <td className="px-4 py-2.5 text-ink">{job.job_type}</td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="px-4 py-2.5 text-ink-muted">
                    {job.attempt} / {job.max_attempts}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-danger">{job.error}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="p-4">
            <EmptyState title="No jobs yet" description="AI generation, publishing, and other background work will appear here." />
          </div>
        )}
      </Card>
    </div>
  );
}
