import { Sparkles } from "lucide-react";
import type * as React from "react";
import { humanize, toneFor, type Tone } from "@/lib/status";
import { cn } from "@/lib/utils";

const TONE_CLASSES: Record<Tone, { badge: string; dot: string }> = {
  success: { badge: "bg-success-subtle text-success", dot: "bg-success" },
  warning: { badge: "bg-warning-subtle text-warning", dot: "bg-warning" },
  danger: { badge: "bg-danger-subtle text-danger", dot: "bg-danger" },
  info: { badge: "bg-info-subtle text-info", dot: "bg-info" },
  neutral: { badge: "bg-neutral-subtle text-neutral", dot: "bg-neutral" },
  brand: { badge: "bg-brand-subtle text-brand", dot: "bg-brand" },
  ai: { badge: "bg-ai-subtle text-ai", dot: "bg-ai" },
};

export function Badge({ tone = "neutral", dot = true, className, children }: {
  tone?: Tone; dot?: boolean; className?: string; children: React.ReactNode;
}) {
  const t = TONE_CLASSES[tone];
  return (
    <span className={cn("inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-full px-2 text-caption font-medium", t.badge, className)}>
      {dot && <span aria-hidden className={cn("size-1.5 rounded-full", t.dot)} />}
      {children}
    </span>
  );
}

/** Domain status → consistent tone + label (dot + text, never colour alone). */
export function StatusBadge({ status, label, className }: { status: string; label?: string; className?: string }) {
  return <Badge tone={toneFor(status)} className={className}>{label ?? humanize(status)}</Badge>;
}

/** Marks AI-generated content everywhere it appears. */
export function AiBadge({ label = "AI-generated", className }: { label?: string; className?: string }) {
  return (
    <span className={cn("inline-flex h-[22px] items-center gap-1 rounded-full bg-ai-subtle px-2 text-caption font-medium text-ai", className)}>
      <Sparkles className="size-3" aria-hidden />
      {label}
    </span>
  );
}

/** Neutral metadata chip (roles, tags). */
export function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex h-6 items-center rounded-[var(--radius-control)] border border-border bg-surface-subtle px-2 text-caption font-medium text-fg-secondary", className)}>
      {children}
    </span>
  );
}
