import { Ban, Building2, CalendarClock, CheckCircle2, Layers, Pencil, Ruler, UserRound } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { DocumentHeader, MetaItem } from "@/components/system/business";
import { MoneyText } from "@/components/system/data-display";
import { ConfirmDialog } from "@/components/system/forms";
import { DescriptionList, Panel } from "@/components/system/layout-blocks";
import { ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api-client";
import { formatDateTime, formatMoney, formatRelative } from "@/lib/format";
import { humanize } from "@/lib/status";
import { useUnit, useUnitReservation, useUpdateUnit, type PlanBreakdown, type UnitDetail } from "./api";
import { bedroomsLabel } from "./logic";
import { UnitFormDialog } from "./manage-dialogs";
import { DemoBadge, DemoDataNotice } from "./shared";

export default function UnitDetailPage() {
  const { id } = useParams();
  const q = useUnit(id);
  if (q.isPending) return <DetailSkeleton />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} className="min-h-[50vh]" />;
  return <UnitView unit={q.data} />;
}

function UnitView({ unit: u }: { unit: UnitDetail }) {
  const update = useUpdateUnit(u.id);
  const reservation = useUnitReservation(u.id);
  const [confirm, setConfirm] = React.useState<string | null>(null);
  const [editing, setEditing] = React.useState(false);
  const label = `${u.building.code}-${u.unit_number}`;

  const changeStatus = (status: string) => update.mutate({ status }, {
    onSuccess: () => { toast.success(`${label} is now ${status}`); setConfirm(null); },
    onError: (e) => { toast.error(e instanceof ApiError ? e.message : "Couldn't change the status"); setConfirm(null); },
  });

  return (
    <>
      <DocumentHeader
        back={{ to: `/realestate/projects/${u.project.id}`, label: u.project.name }}
        code={label}
        title={`${humanize(u.unit_type)} · ${bedroomsLabel(u.bedrooms)}`}
        status={u.status}
        amount={u.list_price}
        amountLabel="List price"
        meta={<>
          <MetaItem icon={<Building2 />}>{u.building.name}</MetaItem>
          <MetaItem icon={<Layers />}>Floor {u.floor}</MetaItem>
          <MetaItem icon={<Ruler />}>{Number(u.area_sqm).toLocaleString("en-US")} m² · {formatMoney(u.price_per_sqm)}/m²</MetaItem>
          {u.is_demo_data && <DemoBadge />}
        </>}
        actions={<>
          {u.can_manage && <Button onClick={() => setEditing(true)}><Pencil /> Edit unit</Button>}
          {u.allowed_status_changes.includes("blocked") && <Button variant="ghost" onClick={() => setConfirm("blocked")}><Ban /> Block unit</Button>}
          {u.allowed_status_changes.includes("available") && <Button onClick={() => setConfirm("available")}><CheckCircle2 /> Make available</Button>}
        </>}
      />
      <DemoDataNotice />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-4">
          <Panel title="Payment plans" description="Exact amounts for this unit's list price (fictional)">
            {u.payment_plans.length === 0 ? <p className="p-4 text-small text-fg-muted">No active payment plans.</p> : (
              <div className="grid gap-px bg-border-subtle md:grid-cols-2">{u.payment_plans.map((p) => <Breakdown key={p.plan_id} plan={p} />)}</div>
            )}
          </Panel>
          {u.notes && <Panel title="Notes"><p className="whitespace-pre-line p-4 text-body text-fg-secondary">{u.notes}</p></Panel>}
        </div>

        <aside className="space-y-4">
          <Panel title="Reservation" description={u.status === "reserved" ? "Held for a buyer" : u.status === "sold" ? "Sold" : "Reserve from a lead's page"}>
            {reservation.isPending ? <ListSkeleton rows={2} /> : reservation.isError ? <ErrorState error={reservation.error} onRetry={() => void reservation.refetch()} />
              : reservation.data ? (
                <DescriptionList items={[
                  { label: "Reservation", value: <span className="tabular">{reservation.data.code}</span> },
                  { label: "Lead", value: reservation.data.lead
                    ? <Link className="text-brand hover:underline" to={`/crm/leads/${reservation.data.lead.id}`}>{reservation.data.lead.code} · {reservation.data.lead.name}</Link>
                    : <span className="text-fg-muted">Restricted</span> },
                  { label: "Reserved by", value: <span className="inline-flex items-center gap-1"><UserRound className="size-3.5 text-fg-muted" />{reservation.data.reserved_by ?? "—"}</span> },
                  { label: "Expires", value: <span className="inline-flex items-center gap-1" title={formatDateTime(reservation.data.expires_at)}><CalendarClock className="size-3.5 text-fg-muted" />{formatRelative(reservation.data.expires_at)}</span> },
                ]} />
              ) : (
                <p className="p-4 text-small text-fg-muted">{u.status === "sold" ? "This unit has been sold." : "No active reservation."}</p>
              )}
          </Panel>
          <Panel title="Details">
            <DescriptionList items={[
              { label: "Project", value: <Link className="text-brand hover:underline" to={`/realestate/projects/${u.project.id}`}>{u.project.name}</Link> },
              { label: "Building", value: `${u.building.code} · ${u.building.name}` },
              { label: "Bedrooms", value: u.bedrooms },
              { label: "Bathrooms", value: u.bathrooms },
              { label: "View", value: u.view ?? "—" },
              { label: "Public listing", value: u.is_public ? "Yes" : "No" },
              { label: "Updated", value: formatDateTime(u.updated_at) },
            ]} />
          </Panel>
        </aside>
      </div>

      {editing && <UnitFormDialog unit={u} onClose={() => setEditing(false)} />}
      <ConfirmDialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)} loading={update.isPending}
        tone={confirm === "blocked" ? "danger" : "primary"}
        title={confirm === "blocked" ? `Block ${label}?` : `Make ${label} available?`}
        confirmLabel={confirm === "blocked" ? "Block unit" : "Make available"}
        description={confirm === "blocked" ? "Blocked units can't be reserved until they are made available again." : "The unit can then be reserved for a lead."}
        onConfirm={() => confirm && changeStatus(confirm)} />
    </>
  );
}

const FREQUENCY: Record<string, string> = { monthly: "month", quarterly: "quarter", semi_annual: "half-year", annual: "year" };

function Breakdown({ plan: p }: { plan: PlanBreakdown }) {
  const rows: [string, string | null, string][] = [
    [`Down payment (${Number(p.down_payment_pct)}%)`, p.down_payment, "On signing"],
  ];
  if (p.installments > 0) {
    const same = p.installment_amount === p.last_installment_amount;
    rows.push([`${p.installments} installments`, p.installment_amount, `Per ${FREQUENCY[p.installment_frequency] ?? p.installment_frequency}${same ? "" : `; last ${formatMoney(p.last_installment_amount, { decimals: 2 })}`}`]);
  }
  if (Number(p.handover_pct) > 0 || p.installments === 0) rows.push([`On handover (${Number(p.handover_pct)}%)`, p.handover_payment, "At key handover"]);
  return (
    <section className="bg-surface p-4" aria-label={p.name}>
      <h3 className="font-medium">{p.name}</h3>
      <dl className="mt-3 space-y-2 text-small">
        {rows.map(([k, v, hint]) => (
          <div key={k} className="flex items-start justify-between gap-3">
            <dt><span className="text-fg">{k}</span><span className="block text-caption text-fg-muted">{hint}</span></dt>
            <dd><MoneyText value={v} decimals={2} className="font-medium" /></dd>
          </div>
        ))}
        <div className="flex items-center justify-between gap-3 border-t border-border-subtle pt-2">
          <dt className="font-medium">Total</dt><dd><MoneyText value={p.total} decimals={2} className="font-semibold" /></dd>
        </div>
      </dl>
    </section>
  );
}

function DetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading unit">
      <Skeleton className="mb-2 h-4 w-24" /><Skeleton className="mb-6 h-8 w-72 max-w-full" />
      <div className="grid gap-6 xl:grid-cols-[1fr_360px]"><div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={4} /></div>
        <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={3} /></div></div>
    </div>
  );
}
