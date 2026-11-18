import { CalendarRange, FolderKanban, Plus } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/system/badges";
import { MoneyText } from "@/components/system/data-display";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { formatDate } from "@/lib/format";
import { useProjects } from "./api";
import { ProjectFormDialog } from "./budget-dialogs";

export default function ProjectsPage() {
  const q = useProjects();
  const canManage = useCan("finance.projects.manage");
  const canSeeBudgets = useCan("finance.budgets.read");
  const [creating, setCreating] = React.useState(false);

  return (
    <>
      <PageHeader title="Operational projects" description="Internal projects that hold their own budgets, such as construction phases and rollouts."
        actions={canManage && <Button variant="primary" onClick={() => setCreating(true)}><Plus /> New project</Button>} />
      {q.isPending ? (
        <div className="grid gap-4 lg:grid-cols-2">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-44 rounded-[var(--radius-panel)]" />)}</div>
      ) : q.isError ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : !q.data.length ? (
        <div className="rounded-[var(--radius-panel)] border border-border bg-surface">
          <EmptyState icon={<FolderKanban className="size-5" />} title="No projects yet" description="Create a project to give it a budget and charge purchases to it." />
        </div>
      ) : (
        <ul className="grid gap-4 lg:grid-cols-2">
          {q.data.map((p) => {
            const capacity = Number(p.allocated_total);
            const usedPct = capacity > 0 ? Math.min(100, (Number(p.committed_total) / capacity) * 100) : 0;
            return (
              <li key={p.id} className="flex flex-col rounded-[var(--radius-panel)] border border-border bg-surface p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="tabular text-caption font-medium text-fg-muted">{p.code} · {p.department.name}</p>
                    <h2 className="mt-0.5 text-lead font-semibold">{p.name}</h2>
                  </div>
                  <StatusBadge status={p.status} />
                </div>
                {p.description && <p className="mt-1 line-clamp-2 text-small text-fg-secondary">{p.description}</p>}
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-small text-fg-secondary">
                  {p.manager && <span>PM: <Link className="hover:text-brand" to={`/hr/employees/${p.manager.id}`}>{p.manager.full_name}</Link></span>}
                  {(p.start_date || p.end_date) && <span className="inline-flex items-center gap-1"><CalendarRange className="size-3.5 text-fg-muted" />{formatDate(p.start_date)} – {formatDate(p.end_date)}</span>}
                </div>
                {canSeeBudgets && (
                  <div className="mt-auto pt-4">
                    <div className="mb-2 flex items-baseline justify-between text-small">
                      <span className="text-fg-muted">Committed <MoneyText value={p.committed_total} className="text-fg" /> of <MoneyText value={p.allocated_total} className="text-fg" /></span>
                      <Link to={`/finance/budgets?project_id=${p.id}`} className="font-medium text-brand hover:underline">Budgets</Link>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-surface-sunken"><div className="h-full rounded-full bg-primary" style={{ width: `${usedPct}%` }} /></div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {canManage && <ProjectFormDialog open={creating} onOpenChange={setCreating} />}
    </>
  );
}
