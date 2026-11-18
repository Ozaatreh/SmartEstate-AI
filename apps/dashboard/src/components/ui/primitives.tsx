/** Small Radix-based primitives themed with SmartEstate tokens (shadcn/ui pattern, owned source). */
import * as AvatarPrimitive from "@radix-ui/react-avatar";
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as LabelPrimitive from "@radix-ui/react-label";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import * as SeparatorPrimitive from "@radix-ui/react-separator";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { Check, Minus } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const overlayPanel =
  "z-50 rounded-[var(--radius-panel)] border border-border bg-surface text-fg shadow-[var(--shadow-overlay)] " +
  "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 " +
  "data-[side=bottom]:slide-in-from-top-1 data-[side=top]:slide-in-from-bottom-1 data-[side=left]:slide-in-from-right-1 data-[side=right]:slide-in-from-left-1";

// --- Label ------------------------------------------------------------------------------
export const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root ref={ref} className={cn("text-small font-medium text-fg", className)} {...props} />
));
Label.displayName = "Label";

// --- Separator ------------------------------------------------------------------------------
export function Separator({ className, orientation = "horizontal", ...props }: React.ComponentProps<typeof SeparatorPrimitive.Root>) {
  return (
    <SeparatorPrimitive.Root
      orientation={orientation}
      className={cn("shrink-0 bg-border", orientation === "horizontal" ? "h-px w-full" : "h-full w-px", className)}
      {...props}
    />
  );
}

// --- Skeleton ---------------------------------------------------------------------------------
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden className={cn("skeleton-shimmer rounded-[var(--radius-control)]", className)} {...props} />;
}

// --- Checkbox ---------------------------------------------------------------------------------
export const Checkbox = React.forwardRef<
  React.ElementRef<typeof CheckboxPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>
>(({ className, ...props }, ref) => (
  <CheckboxPrimitive.Root
    ref={ref}
    className={cn(
      "peer grid size-4 shrink-0 place-items-center rounded-[4px] border border-border-strong bg-surface transition-colors",
      "data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground",
      "data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground",
      "disabled:opacity-50",
      className,
    )}
    {...props}
  >
    <CheckboxPrimitive.Indicator>
      {props.checked === "indeterminate" ? <Minus className="size-3" strokeWidth={3} /> : <Check className="size-3" strokeWidth={3} />}
    </CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
));
Checkbox.displayName = "Checkbox";

// --- Switch ---------------------------------------------------------------------------------------
export function Switch({ checked, onCheckedChange, disabled, label, className }: {
  checked: boolean; onCheckedChange: (v: boolean) => void; disabled?: boolean; label: string; className?: string;
}) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => onCheckedChange(!checked)}
      className={cn("relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-150 disabled:opacity-50",
        checked ? "bg-success" : "bg-border-strong", className)}>
      <span aria-hidden className={cn("inline-block size-4 rounded-full bg-white shadow-sm transition-transform duration-150", checked ? "translate-x-[18px]" : "translate-x-0.5")} />
    </button>
  );
}

// --- Avatar -------------------------------------------------------------------------------------
export function Avatar({ initials, src, className, label }: { initials: string; src?: string; className?: string; label?: string }) {
  return (
    <AvatarPrimitive.Root className={cn("relative inline-flex size-8 shrink-0 overflow-hidden rounded-full", className)} aria-label={label}>
      {src && <AvatarPrimitive.Image src={src} alt="" className="size-full object-cover" />}
      <AvatarPrimitive.Fallback className="grid size-full place-items-center bg-brand-subtle text-caption font-semibold text-brand">
        {initials}
      </AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  );
}

// --- Tooltip ---------------------------------------------------------------------------------------
export const TooltipProvider = TooltipPrimitive.Provider;

export function Tooltip({ content, children, side = "top", disabled }: {
  content: React.ReactNode; children: React.ReactNode; side?: "top" | "right" | "bottom" | "left"; disabled?: boolean;
}) {
  if (disabled) return <>{children}</>;
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          className="z-50 rounded-[var(--radius-control)] bg-primary px-2 py-1 text-caption font-medium text-primary-foreground data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0"
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

// --- Popover -----------------------------------------------------------------------------------------
export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export const PopoverContent = React.forwardRef<
  React.ElementRef<typeof PopoverPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = "end", sideOffset = 6, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content ref={ref} align={align} sideOffset={sideOffset} className={cn(overlayPanel, "w-80 outline-none", className)} {...props} />
  </PopoverPrimitive.Portal>
));
PopoverContent.displayName = "PopoverContent";

// --- Tabs (underline style) ------------------------------------------------------------------------------
export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;
export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn("flex items-center gap-5 overflow-x-auto overflow-y-hidden border-b border-border [scrollbar-width:none]", className)}
      {...props}
    />
  );
}
export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "-mb-px border-b-2 border-transparent pb-2.5 pt-1 text-body font-medium text-fg-muted transition-colors duration-150",
        "hover:text-fg data-[state=active]:border-brand data-[state=active]:text-fg",
        className,
      )}
      {...props}
    />
  );
}
