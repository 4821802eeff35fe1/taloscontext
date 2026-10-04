import type { ReactNode } from "react";
import {
  Outlet,
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useSession, useWorkspaces } from "@/hooks/useSession";
import { useWorkspaceStore } from "@/stores/workspace";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/features/auth/LoginPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { AccountsPage } from "@/features/telegram/AccountsPage";
import { ChannelsPage } from "@/features/channels/ChannelsPage";
import { ChannelSetsPage } from "@/features/channels/ChannelSetsPage";
import { ContentListPage } from "@/features/content/ContentListPage";
import { MediaGalleryPage } from "@/features/media/MediaGalleryPage";
import { CostDashboardPage } from "@/features/analytics/CostDashboardPage";
import { JobsPage } from "@/features/jobs/JobsPage";
import { AutopilotPage } from "@/features/autopilot/AutopilotPage";
import { EmptyState } from "@/components/ui/Card";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 10_000 } },
});

function Protected({ children }: { children: (workspaceId: string) => ReactNode }) {
  const session = useSession();
  const workspaces = useWorkspaces();
  const { workspaceId } = useWorkspaceStore();

  if (session.isLoading) return <div className="p-8 text-ink-muted">Loading…</div>;
  if (session.isError) {
    window.location.href = "/login";
    return null;
  }

  if (workspaces.isLoading) return <div className="p-8 text-ink-muted">Loading workspace…</div>;

  if (!workspaceId) {
    return (
      <AppShell>
        <EmptyState title="No workspace" description="Create a workspace to get started." />
      </AppShell>
    );
  }

  return <AppShell>{children(workspaceId)}</AppShell>;
}

const rootRoute = createRootRoute({ component: () => <Outlet /> });

const loginRoute = createRoute({ getParentRoute: () => rootRoute, path: "/login", component: LoginPage });

function page(path: string, Component: (props: { workspaceId: string }) => ReactNode) {
  return createRoute({
    getParentRoute: () => rootRoute,
    path,
    component: () => <Protected>{(workspaceId) => <Component workspaceId={workspaceId} />}</Protected>,
  });
}

const indexRoute = page("/", DashboardPage);
const accountsRoute = page("/accounts", AccountsPage);
const channelsRoute = page("/channels", ChannelsPage);
const channelSetsRoute = page("/channel-sets", ChannelSetsPage);
const contentRoute = page("/content", (props) => <ContentListPage {...props} title="Posts" />);
const approvalRoute = page("/approval", (props) => (
  <ContentListPage {...props} title="Approval queue" statusFilter="PENDING_APPROVAL" />
));
const mediaRoute = page("/media", MediaGalleryPage);
const costsRoute = page("/costs", CostDashboardPage);
const jobsRoute = page("/jobs", JobsPage);
const autopilotRoute = page("/autopilot", AutopilotPage);

const routeTree = rootRoute.addChildren([
  loginRoute,
  indexRoute,
  accountsRoute,
  channelsRoute,
  channelSetsRoute,
  contentRoute,
  approvalRoute,
  mediaRoute,
  costsRoute,
  jobsRoute,
  autopilotRoute,
]);

const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
