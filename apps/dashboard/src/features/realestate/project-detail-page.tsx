import { CalendarClock, ExternalLink, LayoutGrid, MapPin, Pencil, Plus } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Chip, StatusBadge } from "@/components/system/badges";
import { KpiCard } from "@/components/system/data-display";
import { DescriptionList, PageHeader, Panel } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Skeleton, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { formatDate, formatMoney } from "@/lib/format";
import { humanize } from "@/lib/status";
import { useAvailability, useProject, type Building, type PaymentPlan, type ProjectDetail } from "./api";
import { ModelsPanel } from "./models3d-panel";
import { BuildingFormDialog, PlanFormDialog, ProjectFormDialog, UnitFormDialog } from "./manage-dialogs";
import { AvailabilityGrid, DemoBadge, DemoDataNotice, StatusBar } from "./shared";

export default function ProjectDetailPage() {
  const { id } = useParams();
  const q = useProject(id);
  if (q.isPending) return <DetailSkeleton />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} className="min-h-[50vh]" />;
  return <ProjectView project={q.data} />;
}

type Dialog = { kind: "project" } | { kind: "unit" } | { kind: "building"; building?: Building } | { kind: "plan"; plan?: PaymentPlan };

function ProjectView({ project: p }: { project: ProjectDetail }) {
  const grid = useAvailability(p.id);
  const [dialog, setDialog] = React.useState<Dialog | null>(null);
  const close = () => setDialog(null);
  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Property Portfolio", to: "/realestate/projects" }, { label: p.code }]}
        title={<span className="font-display">{p.name}</span>}
        description={p.description ?? undefined}
        meta={<>
          <StatusBadge status={p.status} />
          {p.is_demo_data && <DemoBadge />}
          <Badge tone={p.is_published ? "success" : "neutral"}>{p.is_published ? "Published" : "Not published"}</Badge>
          <span className="flex items-center gap-1 text-small text-fg-secondary"><MapPin className="size-3.5" aria-hidden />{[p.district, p.city].filter(Boolean).join(", ")}</span>
          {p.handover_date && <span className="flex items-center gap-1 text-small text-fg-secondary"><CalendarClock className="size-3.5" aria-hidden />Handover {formatDate(p.handover_date)}</span>}
        </>}
        actions={<>
          <Button asChild><Link to={`/realestate/units?project_id=${p.id}`}><LayoutGrid /> Browse units</Link></Button>
          {p.can_manage && <Button onClick={() => setDialog({ kind: "project" })}><Pencil /> Edit project</Button>}
          {p.can_manage && p.buildings.length > 0 && <Button variant="primary" onClick={() => setDialog({ kind: "unit" })}><Plus /> Add unit</Button>}
        </>}
      />
      <DemoDataNotice />

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Available" value={<span className="tabular">{p.units.available}</span>} hint={`of ${p.units.total} units`} to={`/realestate/units?project_id=${p.id}&status=available`} />
        <KpiCard label="Reserved" value={<span className="tabular">{p.units.reserved}</span>} hint="active reservations" to={`/realestate/units?project_id=${p.id}&status=reserved`} />
        <KpiCard label="Sold" value={<span className="tabular">{p.units.sold}</span>} hint="converted reservations" to={`/realestate/units?project_id=${p.id}&status=sold`} />
        <KpiCard label="Price range" value={<span className="tabular text-h3">{p.price_from ? formatMoney(p.price_from) : "—"}</span>} hint={p.price_to ? `up to ${formatMoney(p.price_to)}` : undefined} />
      </div>

      <Tabs defaultValue="availability">
        <TabsList className="mb-4">
          <TabsTrigger value="availability">Availability</TabsTrigger>
          <TabsTrigger value="buildings">Buildings <span className="tabular ml-1 text-fg-muted">{p.buildings.length}</span></TabsTrigger>
          <TabsTrigger value="plans">Payment plans <span className="tabular ml-1 text-fg-muted">{p.payment_plans.length}</span></TabsTrigger>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="models">3D models</TabsTrigger>
        </TabsList>

        <TabsContent value="availability" className="space-y-4">
          <StatusBar counts={p.units} />
          {grid.isPending ? <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={4} /></div>
            : grid.isError ? <ErrorState error={grid.error} onRetry={() => void grid.refetch()} />
            : <AvailabilityGrid data={grid.data} />}
        </TabsContent>

        <TabsContent value="buildings">
          <Panel title="Buildings" description="Towers and blocks in this project"
            actions={p.can_manage && <Button size="sm" onClick={() => setDialog({ kind: "building" })}><Plus /> Add building</Button>}>
            {p.buildings.length === 0 ? (
              <EmptyState title="No buildings yet" description={p.can_manage ? "Add a building, then add its units." : "Buildings will appear here."} />
            ) : (
              <ul className="divide-y divide-border-subtle">
                {p.buildings.map((b) => (
                  <li key={b.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <p className="font-medium">{b.name} <span className="tabular font-normal text-fg-muted">· {b.code}</span></p>
                      <p className="text-small text-fg-muted">{b.floors} floors · {b.units.total} units · {b.units.available} available</p>
                    </div>
                    {p.can_manage && <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: "building", building: b })}><Pencil /> Edit</Button>}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </TabsContent>

        <TabsContent value="plans" className="space-y-4">
          {p.can_manage && <div className="flex justify-end"><Button size="sm" onClick={() => setDialog({ kind: "plan" })}><Plus /> Add payment plan</Button></div>}
          {p.payment_plans.length === 0 ? (
            <Panel><EmptyState title="No payment plans" description="Payment plans for this project will appear here." /></Panel>
          ) : (
            <ul className="grid gap-4 md:grid-cols-2">
              {p.payment_plans.map((plan) => <PlanCard key={plan.id} plan={plan} onEdit={p.can_manage ? () => setDialog({ kind: "plan", plan }) : undefined} />)}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="models"><ModelsPanel projectId={p.id} canManage={p.can_manage} isDemo={p.is_demo_data} /></TabsContent>

        <TabsContent value="overview" className="grid gap-4 lg:grid-cols-2">
          <Panel title="Amenities">
            {p.amenities.length ? <div className="flex flex-wrap gap-2 p-4">{p.amenities.map((a) => <Chip key={a}>{a}</Chip>)}</div>
              : <p className="p-4 text-small text-fg-muted">No amenities listed.</p>}
          </Panel>
          <Panel title="Media" description="Illustrative material only">
            {p.media.length ? (
              <ul className="divide-y divide-border-subtle">
                {p.media.map((m, i) => (
                  <li key={`${m.url ?? m.file}-${i}`} className="flex items-center justify-between gap-3 px-4 py-2.5">
                    <span className="min-w-0 truncate text-body">{m.caption ?? m.url ?? m.file}</span>
                    {m.url ? (
                      <a href={m.url} target="_blank" rel="noopener noreferrer" className="inline-flex shrink-0 items-center gap-1 text-small text-brand hover:underline">
                        {humanize(m.kind ?? "link")} <ExternalLink className="size-3.5" aria-hidden />
                      </a>
                    ) : (
                      <span className="shrink-0 text-small text-fg-muted">Local image{m.approved ? " · approved" : ""}</span>
                    )}
                  </li>
                ))}
              </ul>
            ) : <p className="p-4 text-small text-fg-muted">No media links.</p>}
          </Panel>
          <Panel title="Location" className="lg:col-span-2"
            description={p.location_verified ? "Verified — the website shows the map pin and directions" : "Not verified — the website shows only the city and district"}>
            <DescriptionList items={[
              { label: "City / district", value: [p.district, p.city].filter(Boolean).join(", ") },
              { label: "Country", value: p.country ?? "—" },
              { label: "Address", value: p.address ?? "—" },
              { label: "Coordinates", value: p.latitude && p.longitude ? `${Number(p.latitude)}, ${Number(p.longitude)}` : "Not set" },
              {
                label: "Verified",
                value: p.location_verified
                  ? `Yes${p.location_verified_by ? ` · ${p.location_verified_by}` : ""}${p.location_verified_at ? ` · ${formatDate(p.location_verified_at)}` : ""}`
                  : p.is_demo_data ? "No — fictional demo project (can't be pinned to a real place)" : "No",
              },
              {
                label: "Illustrative map point",
                value: p.illustrative_label && p.illustrative_latitude && p.illustrative_longitude
                  ? `${p.illustrative_label} · ${Number(p.illustrative_latitude)}, ${Number(p.illustrative_longitude)}${p.illustrative_source ? ` · source: ${p.illustrative_source}` : ""} — shown as "Illustrative Location — Not the Actual Property Location"`
                  : "None",
              },
            ]} />
          </Panel>
          <Panel title="Details" className="lg:col-span-2">
            <DescriptionList items={[
              { label: "Code", value: p.code },
              { label: "Status", value: humanize(p.status) },
              { label: "Launch", value: formatDate(p.launch_date) },
              { label: "Handover", value: formatDate(p.handover_date) },
              { label: "Buildings", value: p.buildings.map((b) => `${b.code} · ${b.name} (${b.floors} floors)`).join(", ") || "—" },
            ]} />
          </Panel>
        </TabsContent>
      </Tabs>
      {dialog?.kind === "project" && <ProjectFormDialog project={p} onClose={close} />}
      {dialog?.kind === "unit" && <UnitFormDialog projectId={p.id} onClose={close} />}
      {dialog?.kind === "building" && <BuildingFormDialog projectId={p.id} building={dialog.building} onClose={close} />}
      {dialog?.kind === "plan" && <PlanFormDialog projectId={p.id} plan={dialog.plan} onClose={close} />}
    </>
  );
}

const FREQUENCY: Record<string, string> = { monthly: "monthly", quarterly: "quarterly", semi_annual: "semi-annual", annual: "annual" };

function PlanCard({ plan, onEdit }: { plan: PaymentPlan; onEdit?: () => void }) {
  const down = Number(plan.down_payment_pct);
  const handover = Number(plan.handover_pct);
  const middle = Math.max(0, 100 - down - handover);
  return (
    <li className="rounded-[var(--radius-panel)] border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-medium">{plan.name}</h3>
        <div className="flex shrink-0 items-center gap-1">
          {!plan.is_active && <StatusBadge status="inactive" />}
          {plan.marketing_status !== "cleared" && <Badge tone="neutral">{plan.marketing_status === "excluded" ? "Excluded from marketing" : "Not cleared for marketing"}</Badge>}
          {onEdit && <Button size="sm" variant="ghost" onClick={onEdit} aria-label={`Edit ${plan.name}`}><Pencil /></Button>}
        </div>
      </div>
      {plan.description && <p className="mt-1 text-small text-fg-secondary">{plan.description}</p>}
      <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-surface-sunken" role="img" aria-label={`${down}% down payment, ${middle}% in installments, ${handover}% on handover`}>
        <span className="bg-brand" style={{ width: `${down}%` }} />
        <span className="bg-info" style={{ width: `${middle}%` }} />
        <span className="bg-success" style={{ width: `${handover}%` }} />
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-small">
        <div><dt className="text-fg-muted">Down payment</dt><dd className="tabular font-medium">{down}%</dd></div>
        <div><dt className="text-fg-muted">Installments</dt><dd className="tabular font-medium">{plan.installments ? `${middle}% · ${plan.installments} ${FREQUENCY[plan.installment_frequency] ?? plan.installment_frequency}` : "—"}</dd></div>
        <div><dt className="text-fg-muted">On handover</dt><dd className="tabular font-medium">{handover}%</dd></div>
      </dl>
    </li>
  );
}

function DetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading project">
      <Skeleton className="mb-2 h-4 w-32" /><Skeleton className="mb-6 h-9 w-80 max-w-full" />
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>
      <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={5} /></div>
    </div>
  );
}
