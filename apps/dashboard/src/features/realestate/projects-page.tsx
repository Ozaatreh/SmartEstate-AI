import { Building2, CalendarClock, MapPin, Plus } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/system/badges";
import { PageHeader } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { formatDate, formatMoney } from "@/lib/format";
import { useProjects, type Project } from "./api";
import { ProjectFormDialog } from "./manage-dialogs";
import { DemoBadge, DemoDataNotice, StatusBar, StatusLegend } from "./shared";

export default function ProjectsPage() {
  const q = useProjects();
  const canManage = useCan("realestate.inventory.manage");
  const [creating, setCreating] = React.useState(false);
  return (
    <>
      <PageHeader title="Property Portfolio" description="Inventory by project: buildings, units, availability and payment plans."
        actions={canManage && <Button variant="primary" onClick={() => setCreating(true)}><Plus /> New project</Button>} />
      <DemoDataNotice />
      {q.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-busy="true" aria-label="Loading projects">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-56 rounded-[var(--radius-panel)]" />)}
        </div>
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : q.data.items.length === 0 ? (
        <EmptyState icon={<Building2 className="size-5" />} title="No projects yet" description="Projects appear here once inventory is added."
          action={canManage && <Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus /> New project</Button>} />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {q.data.items.map((p) => <ProjectCard key={p.id} project={p} />)}
        </ul>
      )}
      {creating && <ProjectFormDialog onClose={() => setCreating(false)} />}
    </>
  );
}

function ProjectCard({ project: p }: { project: Project }) {
  const sold = p.units.sold + p.units.reserved;
  return (
    <li>
      <Link to={`/realestate/projects/${p.id}`} className="group flex h-full flex-col rounded-[var(--radius-panel)] border border-border bg-surface p-5 transition-colors hover:border-border-strong">
        <div className="flex flex-wrap items-center gap-2">
          <span className="tabular text-small font-medium text-fg-muted">{p.code}</span>
          <StatusBadge status={p.status} />
          {p.is_demo_data && <DemoBadge />}
        </div>
        <h2 className="mt-2 font-display text-h3 font-semibold tracking-[-0.01em] group-hover:text-brand">{p.name}</h2>
        <p className="mt-1 flex items-center gap-1 text-small text-fg-secondary"><MapPin className="size-3.5" aria-hidden />{[p.district, p.city].filter(Boolean).join(", ")}</p>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-small">
          <div><dt className="text-fg-muted">Units</dt><dd className="tabular font-medium">{p.units.total} in {p.building_count} building{p.building_count === 1 ? "" : "s"}</dd></div>
          <div><dt className="text-fg-muted">Prices</dt><dd className="tabular font-medium">{p.price_from ? `${formatMoney(p.price_from)} +` : "—"}</dd></div>
          {p.handover_date && <div className="col-span-2 flex items-center gap-1 text-fg-secondary"><CalendarClock className="size-3.5" aria-hidden />Handover {formatDate(p.handover_date)}</div>}
        </dl>
        <div className="mt-auto pt-4">
          <p className="mb-1.5 text-caption text-fg-muted">{sold} of {p.units.total} reserved or sold</p>
          <StatusBar counts={p.units} />
          <StatusLegend counts={p.units} className="mt-3" />
        </div>
      </Link>
    </li>
  );
}
