import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";
import { FieldContext } from "./field-context";
import { controlClass } from "./input";
import { overlayPanel } from "./primitives";

// --- Dropdown menu -------------------------------------------------------------------------------
export const DropdownMenu = DropdownMenuPrimitive.Root;
export const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;

export const DropdownMenuContent = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content>
>(({ className, sideOffset = 6, align = "end", ...props }, ref) => (
  <DropdownMenuPrimitive.Portal>
    <DropdownMenuPrimitive.Content ref={ref} sideOffset={sideOffset} align={align} className={cn(overlayPanel, "min-w-48 p-1", className)} {...props} />
  </DropdownMenuPrimitive.Portal>
));
DropdownMenuContent.displayName = "DropdownMenuContent";

export const DropdownMenuItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item> & { tone?: "default" | "danger" }
>(({ className, tone = "default", ...props }, ref) => (
  <DropdownMenuPrimitive.Item
    ref={ref}
    className={cn(
      "flex h-8 cursor-default select-none items-center gap-2 rounded-[4px] px-2 text-body outline-none transition-colors",
      "data-[highlighted]:bg-surface-sunken data-[disabled]:pointer-events-none data-[disabled]:opacity-50 [&_svg]:size-4 [&_svg]:text-fg-muted",
      tone === "danger" && "text-danger [&_svg]:text-danger",
      className,
    )}
    {...props}
  />
));
DropdownMenuItem.displayName = "DropdownMenuItem";

export function DropdownMenuLabel({ className, ...props }: React.ComponentProps<typeof DropdownMenuPrimitive.Label>) {
  return <DropdownMenuPrimitive.Label className={cn("px-2 py-1.5 text-caption font-medium text-fg-muted", className)} {...props} />;
}

export function DropdownMenuSeparator({ className, ...props }: React.ComponentProps<typeof DropdownMenuPrimitive.Separator>) {
  return <DropdownMenuPrimitive.Separator className={cn("-mx-1 my-1 h-px bg-border", className)} {...props} />;
}

export const DropdownMenuCheckboxItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.CheckboxItem>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.CheckboxItem>
>(({ className, children, ...props }, ref) => (
  <DropdownMenuPrimitive.CheckboxItem
    ref={ref}
    className={cn("relative flex h-8 cursor-default select-none items-center rounded-[4px] pl-7 pr-2 text-body outline-none data-[highlighted]:bg-surface-sunken", className)}
    {...props}
  >
    <DropdownMenuPrimitive.ItemIndicator className="absolute left-2"><Check className="size-3.5" /></DropdownMenuPrimitive.ItemIndicator>
    {children}
  </DropdownMenuPrimitive.CheckboxItem>
));
DropdownMenuCheckboxItem.displayName = "DropdownMenuCheckboxItem";

// --- Select -----------------------------------------------------------------------------------------
export interface SelectOption { value: string; label: string }

export function Select({ value, onValueChange, options, placeholder = "Select…", className, id, invalid, disabled, "aria-label": ariaLabel }: {
  value: string | undefined; onValueChange: (v: string) => void; options: SelectOption[]; placeholder?: string;
  className?: string; id?: string; invalid?: boolean; disabled?: boolean; "aria-label"?: string;
}) {
  const field = React.useContext(FieldContext);
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectPrimitive.Trigger
        id={id ?? field?.id}
        aria-label={ariaLabel}
        aria-describedby={field?.describedBy}
        aria-invalid={(invalid ?? field?.invalid) || undefined}
        className={cn(controlClass, "flex h-9 min-w-0 items-center justify-between gap-2 text-left data-[placeholder]:text-fg-muted", className)}
      >
        <span className="min-w-0 flex-1 truncate"><SelectPrimitive.Value placeholder={placeholder} /></span>
        <SelectPrimitive.Icon><ChevronDown className="size-4 text-fg-muted" /></SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content position="popper" sideOffset={4} className={cn(overlayPanel, "max-h-72 min-w-[var(--radix-select-trigger-width)] p-1")}>
          <SelectPrimitive.Viewport>
            {options.map((o) => (
              <SelectPrimitive.Item
                key={o.value}
                value={o.value}
                className="relative flex h-8 cursor-default select-none items-center rounded-[4px] pl-7 pr-2 text-body outline-none data-[highlighted]:bg-surface-sunken"
              >
                <SelectPrimitive.ItemIndicator className="absolute left-2"><Check className="size-3.5" /></SelectPrimitive.ItemIndicator>
                <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
