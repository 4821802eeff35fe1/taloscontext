import * as RadixContext from "@radix-ui/react-context-menu";
import * as RadixDialog from "@radix-ui/react-dialog";
import * as RadixDropdown from "@radix-ui/react-dropdown-menu";
import * as RadixPopover from "@radix-ui/react-popover";
import * as RadixTooltip from "@radix-ui/react-tooltip";
import { X, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";
import { Button, cn } from "./primitives";

// ---------------------------------------------------------------- Dialog

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  trigger,
  size = "md",
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  trigger?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const width = {
    sm: "max-w-sm",
    md: "max-w-lg",
    lg: "max-w-2xl",
    xl: "max-w-4xl",
  }[size];
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger>}
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px] data-[state=open]:animate-fade-in" />
        <RadixDialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col",
            "rounded-xl border border-surface-border bg-surface-raised shadow-overlay data-[state=open]:animate-scale-in focus:outline-none",
            width,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-surface-border px-5 py-4">
            <div>
              <RadixDialog.Title className="text-base font-semibold text-ink">
                {title}
              </RadixDialog.Title>
              {description ? (
                <RadixDialog.Description className="mt-1 text-sm text-ink-muted">
                  {description}
                </RadixDialog.Description>
              ) : (
                <RadixDialog.Description className="sr-only">
                  {title}
                </RadixDialog.Description>
              )}
            </div>
            <RadixDialog.Close asChild>
              <Button variant="ghost" size="icon-sm" aria-label={i18n.t("common:action.close")}>
                <X className="h-4 w-4" />
              </Button>
            </RadixDialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            {children}
          </div>
          {footer && (
            <div className="flex flex-wrap justify-end gap-2 border-t border-surface-border px-5 py-3">
              {footer}
            </div>
          )}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

/** Destructive or important confirmation — never window.confirm(). */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive,
  loading,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>{t("action.cancel")}</Button>
          <Button
            variant={destructive ? "danger" : "primary"}
            loading={loading}
            onClick={onConfirm}
            autoFocus
          >
            {confirmLabel ?? t("action.confirm")}
          </Button>
        </>
      }
    />
  );
}

export function useConfirm() {
  const [state, setState] = useState<{ open: boolean; action?: () => void }>({
    open: false,
  });
  return {
    ask: (action: () => void) => setState({ open: true, action }),
    props: {
      open: state.open,
      onOpenChange: (v: boolean) => setState((s) => ({ ...s, open: v })),
      onConfirm: () => {
        state.action?.();
        setState({ open: false });
      },
    },
  };
}

// ---------------------------------------------------------------- Drawer

export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  width = "max-w-xl",
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-black/50 data-[state=open]:animate-fade-in" />
        <RadixDialog.Content
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-surface-border bg-surface-raised shadow-overlay",
            "data-[state=open]:animate-slide-in-right focus:outline-none",
            width,
          )}
        >
          <div className="flex items-start justify-between gap-3 border-b border-surface-border px-5 py-4">
            <div className="min-w-0">
              <RadixDialog.Title className="truncate text-base font-semibold text-ink">
                {title}
              </RadixDialog.Title>
              <RadixDialog.Description
                className={
                  description ? "mt-0.5 text-xs text-ink-muted" : "sr-only"
                }
              >
                {description ?? i18n.t("common:action.details")}
              </RadixDialog.Description>
            </div>
            <RadixDialog.Close asChild>
              <Button variant="ghost" size="icon-sm" aria-label={i18n.t("common:action.close")}>
                <X className="h-4 w-4" />
              </Button>
            </RadixDialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            {children}
          </div>
          {footer && (
            <div className="flex flex-wrap justify-end gap-2 border-t border-surface-border px-5 py-3">
              {footer}
            </div>
          )}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

// ---------------------------------------------------------------- Dropdown / Context menu

export type MenuItem =
  | {
      type?: "item";
      label: string;
      icon?: LucideIcon;
      onSelect: () => void;
      danger?: boolean;
      disabled?: boolean;
      shortcut?: string;
      hint?: string;
    }
  | { type: "separator" }
  | { type: "label"; label: string };

const itemClass =
  "flex cursor-default select-none items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-40 data-[highlighted]:bg-surface-hover";

function renderItems(
  items: MenuItem[],
  Item: typeof RadixDropdown.Item | typeof RadixContext.Item,
  Sep: typeof RadixDropdown.Separator,
  Lbl: typeof RadixDropdown.Label,
) {
  return items.map((item, i) => {
    if (item.type === "separator")
      return <Sep key={i} className="my-1 h-px bg-surface-border" />;
    if (item.type === "label")
      return (
        <Lbl
          key={i}
          className="px-2 py-1 text-2xs font-semibold uppercase tracking-wide text-ink-faint"
        >
          {item.label}
        </Lbl>
      );
    const Icon = item.icon;
    return (
      <Item
        key={i}
        disabled={item.disabled}
        onSelect={item.onSelect}
        className={cn(itemClass, item.danger ? "text-danger" : "text-ink")}
      >
        {Icon && <Icon className="h-4 w-4 text-ink-muted" aria-hidden />}
        <span className="flex-1">
          {item.label}
          {item.hint && (
            <span className="block text-2xs text-ink-faint">{item.hint}</span>
          )}
        </span>
        {item.shortcut && (
          <span className="text-2xs text-ink-faint">{item.shortcut}</span>
        )}
      </Item>
    );
  });
}

export function DropdownMenu({
  trigger,
  items,
  align = "end",
}: {
  trigger: ReactNode;
  items: MenuItem[];
  align?: "start" | "end";
}) {
  return (
    <RadixDropdown.Root>
      <RadixDropdown.Trigger asChild>{trigger}</RadixDropdown.Trigger>
      <RadixDropdown.Portal>
        <RadixDropdown.Content
          align={align}
          sideOffset={6}
          className="z-50 min-w-[190px] rounded-lg border border-surface-border bg-surface-overlay p-1 shadow-overlay data-[state=open]:animate-scale-in"
        >
          {renderItems(
            items,
            RadixDropdown.Item,
            RadixDropdown.Separator,
            RadixDropdown.Label,
          )}
        </RadixDropdown.Content>
      </RadixDropdown.Portal>
    </RadixDropdown.Root>
  );
}

export function ContextMenu({
  children,
  items,
}: {
  children: ReactNode;
  items: MenuItem[];
}) {
  return (
    <RadixContext.Root>
      <RadixContext.Trigger asChild>{children}</RadixContext.Trigger>
      <RadixContext.Portal>
        <RadixContext.Content className="z-50 min-w-[190px] rounded-lg border border-surface-border bg-surface-overlay p-1 shadow-overlay">
          {renderItems(
            items,
            RadixContext.Item as typeof RadixDropdown.Item,
            RadixContext.Separator as typeof RadixDropdown.Separator,
            RadixContext.Label as typeof RadixDropdown.Label,
          )}
        </RadixContext.Content>
      </RadixContext.Portal>
    </RadixContext.Root>
  );
}

// ---------------------------------------------------------------- Popover / Tooltip

export function Popover({
  trigger,
  children,
  align = "start",
  open,
  onOpenChange,
  className,
}: {
  trigger: ReactNode;
  children: ReactNode;
  align?: "start" | "center" | "end";
  open?: boolean;
  onOpenChange?: (v: boolean) => void;
  className?: string;
}) {
  return (
    <RadixPopover.Root open={open} onOpenChange={onOpenChange}>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content
          align={align}
          sideOffset={6}
          className={cn(
            "z-50 rounded-xl border border-surface-border bg-surface-overlay p-3 shadow-overlay data-[state=open]:animate-scale-in focus:outline-none",
            className,
          )}
        >
          {children}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}

export const TooltipProvider = RadixTooltip.Provider;

export function Tooltip({
  content,
  children,
  side = "top",
}: {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}) {
  if (!content) return <>{children}</>;
  return (
    <RadixTooltip.Root delayDuration={250}>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          side={side}
          sideOffset={6}
          className="z-[60] max-w-xs rounded-md border border-surface-border bg-surface-overlay px-2.5 py-1.5 text-xs text-ink shadow-overlay animate-fade-in"
        >
          {content}
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  );
}
