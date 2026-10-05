import { useMutation, useQueryClient } from "@tanstack/react-query";
import i18n from "@/i18n";
import { toast } from "@/components/ui/toast";

/** Mutation with workspace cache refresh and localized success/error toasts. */
export function useOperation<T>(
  workspaceId: string,
  fn: (input: T) => Promise<unknown>,
  success?: string,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({
        predicate: (q) => q.queryKey.includes(workspaceId),
      });
      toast.success(success ?? i18n.t("common:toast.saved"));
    },
    // ApiError.message is already localized from its error code.
    onError: (e) => toast.error(e.message),
  });
}
