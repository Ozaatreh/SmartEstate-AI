import { ChevronRight } from "lucide-react";
import type * as React from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export interface Crumb { label: string; to?: string }

/** Title, one-line description, primary actions. Every page starts with one. */
export function PageHeader({ title, description, actions, breadcrumbs, meta, className }: {
  title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; breadcrumbs?: Crumb[];
  meta?: React.ReactNode; className?: string;
}) {
  return (
    <header className={cn("mb-6", className)}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav aria-label="Breadcrumb" className="mb-2 flex items-center gap-1 text-small text-fg-muted">
          {breadcrumbs.map((c, i) => (
            <span key={`${c.label}-${i}`} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="size-3.5" aria-hidden />}
              {c.to ? <Link to={c.to} className="transition-colors hover:text-fg">{c.label}</Link> : <span className="text-fg-secondary">{c.label}</span>}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-h2 font-semibold tracking-[-0.015em] text-fg">{title}</h1>
          {description && <p className="mt-1 max-w-2xl text-body text-fg-secondary">{description}</p>}
          {meta && <div className="mt-3 flex flex-wrap items-center gap-2">{meta}</div>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

/** Bordered surface section — the flat alternative to "cards" (no heavy shadow, 8px radius). */
export function Panel({ title, description, actions, children, className, bodyClassName, footer }: {
  title?: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode;
  className?: string; bodyClassName?: string; footer?: React.ReactNode;
}) {
  return (
    <section className={cn("overflow-hidden rounded-[var(--radius-panel)] border border-border bg-surface", className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-4 border-b border-border-subtle px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="text-body font-semibold text-fg">{title}</h2>}
            {description && <p className="mt-0.5 text-small text-fg-muted">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
      {footer && <div className="border-t border-border-subtle bg-surface-subtle px-4 py-2.5">{footer}</div>}
    </section>
  );
}

/** Label/value list for detail views. */
export function DescriptionList({ items, className }: { items: { label: string; value: React.ReactNode }[]; className?: string }) {
  return (
    <dl className={cn("divide-y divide-border-subtle", className)}>
      {items.map((it) => (
        <div key={it.label} className="grid grid-cols-[minmax(0,140px)_1fr] gap-4 px-4 py-2.5">
          <dt className="text-small text-fg-muted">{it.label}</dt>
          <dd className="min-w-0 text-body text-fg">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}
