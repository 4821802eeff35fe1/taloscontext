import { useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useWorkspaceStore } from "@/stores/workspace";
import { useEffect } from "react";

export function useSession() {
  const query = useQuery({
    queryKey: ["me"],
    queryFn: endpoints.me,
    retry: false,
  });
  return query;
}

export function useWorkspaces() {
  const { workspaceId, setWorkspaceId } = useWorkspaceStore();
  const query = useQuery({
    queryKey: ["workspaces"],
    queryFn: endpoints.workspaces,
  });

  useEffect(() => {
    if (query.data?.length && !query.data.some((w) => w.id === workspaceId)) {
      setWorkspaceId(query.data[0].id);
    }
  }, [query.data, workspaceId, setWorkspaceId]);

  return query;
}

export function useLogout() {
  const client = useQueryClient();
  return async () => {
    await endpoints.logout();
    client.clear();
    useWorkspaceStore.getState().setWorkspaceId(null);
    window.location.assign("/login");
  };
}
