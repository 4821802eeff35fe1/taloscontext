import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/components/ui/toast";
export function useOperation<T>(
  workspaceId: string,
  fn: (input: T) => Promise<unknown>,
  success = "Saved",
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({
        predicate: (q) => q.queryKey.includes(workspaceId),
      });
      toast.success(success);
    },
    onError: (e) => toast.error(e.message),
  });
}
