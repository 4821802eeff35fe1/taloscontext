import * as RadixSelect from "@radix-ui/react-select";
import { Check, ChevronDown } from "./icons";

export function Select({
  value,
  onValueChange,
  options,
  placeholder,
}: {
  value: string | undefined;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
}) {
  return (
    <RadixSelect.Root value={value} onValueChange={onValueChange}>
      <RadixSelect.Trigger className="input flex items-center justify-between gap-2">
        <RadixSelect.Value placeholder={placeholder} />
        <RadixSelect.Icon>
          <ChevronDown className="h-4 w-4 text-ink-faint" />
        </RadixSelect.Icon>
      </RadixSelect.Trigger>
      <RadixSelect.Portal>
        <RadixSelect.Content className="z-50 overflow-hidden rounded-lg border border-surface-border bg-surface-overlay shadow-xl">
          <RadixSelect.Viewport className="p-1">
            {options.map((option) => (
              <RadixSelect.Item
                key={option.value}
                value={option.value}
                className="flex cursor-pointer items-center justify-between rounded-md px-2.5 py-2 text-sm text-ink outline-none data-[highlighted]:bg-accent/15 data-[highlighted]:text-accent-foreground"
              >
                <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                <RadixSelect.ItemIndicator>
                  <Check className="h-3.5 w-3.5" />
                </RadixSelect.ItemIndicator>
              </RadixSelect.Item>
            ))}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  );
}
