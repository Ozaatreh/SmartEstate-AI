import { AlertCircle } from "lucide-react";
import * as React from "react";
import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { FieldContext } from "@/components/ui/field-context";
import { Label } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/** Label + control + hint + error. Wires aria-invalid / aria-describedby onto the child control. */
export function FormField({ label, htmlFor, hint, error, required, children, className, labelAction }: {
  label: string; htmlFor: string; hint?: React.ReactNode; error?: string; required?: boolean;
  children: React.ReactElement<Record<string, unknown>>; className?: string; labelAction?: React.ReactNode;
}) {
  const hintId = hint ? `${htmlFor}-hint` : undefined;
  const errorId = error ? `${htmlFor}-error` : undefined;
  const control = React.cloneElement(children, {
    id: htmlFor,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": [hintId, errorId].filter(Boolean).join(" ") || undefined,
    "aria-required": required || undefined,
  });
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={htmlFor}>
          {label}
          {required && <span className="ml-0.5 text-danger" aria-hidden>*</span>}
        </Label>
        {labelAction}
      </div>
      <FieldContext.Provider value={{ id: htmlFor, describedBy: [hintId, errorId].filter(Boolean).join(" ") || undefined, invalid: Boolean(error), required }}>
        {control}
      </FieldContext.Provider>
      {error ? (
        <p id={errorId} role="alert" className="flex items-center gap-1 text-small text-danger"><AlertCircle className="size-3.5 shrink-0" />{error}</p>
      ) : hint ? (
        <p id={hintId} className="text-small text-fg-muted">{hint}</p>
      ) : null}
    </div>
  );
}

/** Form-level error banner (non-field server errors). */
export function FormAlert({ message, className }: { message: string | null | undefined; className?: string }) {
  if (!message) return null;
  return (
    <div role="alert" className={cn("flex items-start gap-2 rounded-[var(--radius-control)] border border-danger/25 bg-danger-subtle px-3 py-2.5 text-body text-danger", className)}>
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

/** Maps a 422 ApiError onto react-hook-form fields; returns the message for anything left over. */
export function applyServerErrors<T extends FieldValues>(error: unknown, setError: UseFormSetError<T>, fields: readonly Path<T>[]): string | null {
  if (!(error instanceof ApiError)) return "Something went wrong. Try again.";
  const fieldErrors = error.fieldErrors;
  let mapped = false;
  for (const f of fields) {
    if (fieldErrors[f]) {
      setError(f, { type: "server", message: fieldErrors[f] });
      mapped = true;
    }
  }
  return mapped && error.status === 422 ? null : error.message;
}

/** Names the action and the record; destructive actions use the danger tone. */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, tone = "primary", onConfirm, loading }: {
  open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: React.ReactNode; confirmLabel: string;
  tone?: "primary" | "danger"; onConfirm: () => void; loading?: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent hideClose>
        <DialogHeader title={title} description={description} />
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={loading}>Cancel</Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} onClick={onConfirm} loading={loading}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
