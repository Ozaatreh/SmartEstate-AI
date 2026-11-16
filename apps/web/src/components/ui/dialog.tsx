import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

const overlay =
  "fixed inset-0 z-50 bg-[rgb(15_26_43/0.32)] data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0";

export const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & { hideClose?: boolean }
>(({ className, children, hideClose, ...props }, ref) => (
  <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className={overlay} />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-1/2 top-1/2 z-50 grid w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 gap-4",
        "rounded-[var(--radius-dialog)] border border-border bg-surface p-5 shadow-[var(--shadow-overlay)] outline-none",
        "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-[0.98]",
        "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-[0.98]",
        className,
      )}
      {...props}
    >
      {children}
      {!hideClose && (
        <DialogPrimitive.Close className="absolute right-3 top-3 grid size-8 place-items-center rounded-[var(--radius-control)] text-fg-muted transition-colors hover:bg-surface-sunken hover:text-fg">
          <X className="size-4" />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
      )}
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
));
DialogContent.displayName = "DialogContent";

export function DialogHeader({ title, description }: { title: React.ReactNode; description?: React.ReactNode }) {
  return (
    <div className="space-y-1 pr-8">
      <DialogPrimitive.Title className="text-lead font-semibold">{title}</DialogPrimitive.Title>
      {description ? (
        <DialogPrimitive.Description className="text-body text-fg-secondary">{description}</DialogPrimitive.Description>
      ) : (
        <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
      )}
    </div>
  );
}

export function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)} {...props} />;
}

/** Side sheet (mobile navigation, detail drawers). */
export const SheetContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & { side?: "left" | "right"; title: string }
>(({ className, children, side = "left", title, ...props }, ref) => (
  <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className={overlay} />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed inset-y-0 z-50 flex w-[min(320px,88vw)] flex-col bg-surface shadow-[var(--shadow-overlay)] outline-none",
        "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:duration-200 data-[state=closed]:duration-150",
        side === "left"
          ? "left-0 border-r border-border data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left"
          : "right-0 border-l border-border data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right",
        className,
      )}
      {...props}
    >
      <DialogPrimitive.Title className="sr-only">{title}</DialogPrimitive.Title>
      <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
      {children}
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
));
SheetContent.displayName = "SheetContent";
