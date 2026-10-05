import i18n from "@/i18n";
import * as RadixToast from "@radix-ui/react-toast";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { create } from "zustand";
import { cn } from "./primitives";

type Tone = "success" | "error" | "info" | "warning";
type ToastItem = {
  id: number;
  title: string;
  description?: string;
  tone: Tone;
};

const useToastStore = create<{
  items: ToastItem[];
  push: (t: Omit<ToastItem, "id">) => void;
  remove: (id: number) => void;
}>((set) => ({
  items: [],
  push: (t) =>
    set((s) => ({
      items: [...s.items.slice(-3), { ...t, id: Date.now() + Math.random() }],
    })),
  remove: (id) => set((s) => ({ items: s.items.filter((i) => i.id !== id) })),
}));

export const toast = {
  success: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, tone: "success" }),
  error: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, tone: "error" }),
  info: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, tone: "info" }),
  warning: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, tone: "warning" }),
};

const ICON = {
  success: CheckCircle2,
  error: AlertTriangle,
  warning: AlertTriangle,
  info: Info,
};
const COLOR = {
  success: "text-success",
  error: "text-danger",
  warning: "text-warning",
  info: "text-info",
};

export function Toaster() {
  const { items, remove } = useToastStore();
  return (
    <RadixToast.Provider swipeDirection="right" duration={5000}>
      {items.map((t) => {
        const Icon = ICON[t.tone];
        return (
          <RadixToast.Root
            key={t.id}
            onOpenChange={(open) => !open && remove(t.id)}
            className="flex items-start gap-3 rounded-xl border border-surface-border bg-surface-overlay p-3 pr-2 shadow-overlay data-[state=open]:animate-scale-in"
            type={t.tone === "error" ? "foreground" : "background"}
          >
            <Icon
              className={cn("mt-0.5 h-4 w-4 shrink-0", COLOR[t.tone])}
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <RadixToast.Title className="text-sm font-medium text-ink">
                {t.title}
              </RadixToast.Title>
              {t.description && (
                <RadixToast.Description className="mt-0.5 text-xs text-ink-muted">
                  {t.description}
                </RadixToast.Description>
              )}
            </div>
            <RadixToast.Close
              aria-label={i18n.t("common:action.dismiss")}
              className="rounded p-1 text-ink-faint hover:text-ink"
            >
              <X className="h-3.5 w-3.5" />
            </RadixToast.Close>
          </RadixToast.Root>
        );
      })}
      <RadixToast.Viewport className="fixed bottom-4 right-4 z-[100] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2 outline-none" />
    </RadixToast.Provider>
  );
}
