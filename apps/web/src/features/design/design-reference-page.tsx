import type { ColumnDef } from "@tanstack/react-table";
import { Download, FlaskConical, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { AiBadge, Badge, Chip, StatusBadge } from "@/components/system/badges";
import { LogoMark, Wordmark } from "@/components/system/brand";
import { ChartCard } from "@/components/system/chart-card";
import { KpiCard, Meter, MoneyText } from "@/components/system/data-display";
import { DataTable } from "@/components/system/data-table";
import { ConfirmDialog, FormAlert, FormField } from "@/components/system/forms";
import { PageHeader, Panel } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState, ListSkeleton, PermissionState, TableSkeleton } from "@/components/system/states";
import { useListState } from "@/components/system/use-list-state";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { Checkbox, Label, Tabs, TabsContent, TabsList, TabsTrigger, Tooltip } from "@/components/ui/primitives";
import { ApiError, type Page } from "@/lib/api-client";

/*
 * Design-system reference (UI_UX_DESIGN.md § 12). Every component in every state.
 * All values on this page are illustrative samples and are labelled as such; it is restricted to
 * the `system.design_reference.view` permission and is not a business screen.
 */

const COLORS: { group: string; tokens: string[] }[] = [
  { group: "Surfaces", tokens: ["canvas", "surface", "surface-subtle", "surface-sunken", "border", "border-strong"] },
  { group: "Text", tokens: ["text", "text-secondary", "text-muted"] },
  { group: "Brand", tokens: ["primary", "brand", "brand-subtle", "ai", "ai-subtle"] },
  { group: "Status", tokens: ["success", "warning", "danger", "info", "neutral"] },
  { group: "Charts", tokens: ["chart-1", "chart-2", "chart-3", "chart-4", "chart-5"] },
];

const TYPE_SCALE = [
  ["Display", "text-display font-display font-medium", "48 / 56"],
  ["H1", "text-h1 font-semibold tracking-[-0.02em]", "32 / 40"],
  ["H2", "text-h2 font-semibold tracking-[-0.015em]", "24 / 32"],
  ["H3", "text-h3 font-semibold", "20 / 28"],
  ["Lead", "text-lead", "16 / 24"],
  ["Body", "text-body", "14 / 20"],
  ["Small", "text-small", "13 / 18"],
  ["Caption", "text-caption", "12 / 16"],
] as const;

interface SampleRow { id: string; code: string; title: string; status: string; amount: string; owner: string }

const SAMPLE_ROWS: SampleRow[] = [
  { id: "1", code: "PR-00012", title: "Site fencing — Building B", status: "pending_approval", amount: "84500.00", owner: "Khalid Mansour" },
  { id: "2", code: "PR-00011", title: "Concrete pump rental", status: "approved", amount: "212000.00", owner: "Reem Al-Otaibi" },
  { id: "3", code: "PR-00010", title: "Safety equipment", status: "rejected", amount: "9750.50", owner: "Ahmed Karim" },
  { id: "4", code: "PR-00009", title: "Sales gallery furniture", status: "draft", amount: "46200.00", owner: "Sara Al-Harbi" },
];

const SAMPLE_CHART = [
  { month: "Jun", committed: 420, actual: 310 },
  { month: "Jul", committed: 510, actual: 380 },
  { month: "Aug", committed: 480, actual: 450 },
  { month: "Sep", committed: 620, actual: 500 },
  { month: "Oct", committed: 590, actual: 560 },
];

function SampleTag() {
  return <Badge tone="warning" className="ml-2 align-middle"><FlaskConical className="size-3" /> Sample values</Badge>;
}

export default function DesignReferencePage() {
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [plan, setPlan] = React.useState<string | undefined>("standard");
  const tableState = useListState({ defaultSort: "-code" });
  const samplePage: Page<SampleRow> = { items: SAMPLE_ROWS, total: 42, page: 1, page_size: 4, pages: 11 };

  const columns: ColumnDef<SampleRow, unknown>[] = [
    { id: "code", header: "Code", meta: { sortKey: "code", label: "Code", className: "w-28" }, cell: ({ row }) => <span className="tabular font-medium">{row.original.code}</span> },
    { id: "title", header: "Title", meta: { sortKey: "title", label: "Title" }, cell: ({ row }) => row.original.title },
    { id: "owner", header: "Requested by", meta: { label: "Requested by", className: "hidden lg:table-cell" }, cell: ({ row }) => row.original.owner },
    { id: "status", header: "Status", meta: { label: "Status" }, cell: ({ row }) => <StatusBadge status={row.original.status} /> },
    { id: "amount", header: "Amount", meta: { sortKey: "amount", label: "Amount", align: "right" }, cell: ({ row }) => <MoneyText value={row.original.amount} decimals={2} /> },
  ];

  return (
    <>
      <PageHeader
        title="Design system"
        description="SmartEstate AI “Najd” design system: tokens, components and states. Values on this page are illustrative samples, not business data."
        breadcrumbs={[{ label: "Administration" }, { label: "Design system" }]}
        meta={<><Chip>Tokens: src/styles/tokens.css</Chip><Chip>Components: src/components/system</Chip></>}
      />

      <Tabs defaultValue="foundations">
        <TabsList className="mb-6">
          <TabsTrigger value="foundations">Foundations</TabsTrigger>
          <TabsTrigger value="components">Components</TabsTrigger>
          <TabsTrigger value="data">Data display</TabsTrigger>
          <TabsTrigger value="states">States</TabsTrigger>
        </TabsList>

        {/* ---------------------------------------------------------------- Foundations */}
        <TabsContent value="foundations" className="space-y-6">
          <Panel title="Brand" description="Logo mark (stacked rooflines forming an S) and wordmark">
            <div className="flex flex-wrap items-center gap-8 p-6">
              <Wordmark />
              <LogoMark className="size-12" />
              <div className="flex items-center gap-2.5 rounded-[var(--radius-panel)] bg-primary px-4 py-3"><LogoMark /><span className="font-semibold text-primary-foreground">SmartEstate <span className="text-white/60">AI</span></span></div>
            </div>
          </Panel>

          <Panel title="Colour tokens" description="Semantic names only; dark mode redefines the same tokens">
            <div className="grid gap-6 p-4 md:grid-cols-2 xl:grid-cols-3">
              {COLORS.map((g) => (
                <div key={g.group}>
                  <p className="mb-2 text-small font-medium text-fg-secondary">{g.group}</p>
                  <ul className="space-y-1.5">
                    {g.tokens.map((t) => (
                      <li key={t} className="flex items-center gap-3">
                        <span className="size-7 shrink-0 rounded-[var(--radius-control)] border border-border" style={{ background: `var(--${t})` }} />
                        <code className="text-small">--{t}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Typography" description="Inter (UI, tabular figures) · Fraunces (property & campaign display)">
            <ul className="divide-y divide-border-subtle">
              {TYPE_SCALE.map(([name, cls, metrics]) => (
                <li key={name} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-baseline sm:gap-6">
                  <span className="w-24 shrink-0 text-small text-fg-muted">{name} <span className="tabular">{metrics}</span></span>
                  <span className={`${cls} min-w-0 truncate`}>NOVA Residences, Riyadh</span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="Shape & elevation" description="Flat panels with 1px borders; shadow only on overlays">
            <div className="grid gap-4 p-4 sm:grid-cols-3">
              <div className="rounded-[var(--radius-control)] border border-border p-4 text-small">Control · 6px</div>
              <div className="rounded-[var(--radius-panel)] border border-border p-4 text-small">Panel · 8px</div>
              <div className="rounded-[var(--radius-dialog)] border border-border p-4 text-small shadow-[var(--shadow-overlay)]">Overlay · 10px + shadow</div>
            </div>
          </Panel>
        </TabsContent>

        {/* ---------------------------------------------------------------- Components */}
        <TabsContent value="components" className="space-y-6">
          <Panel title="Buttons">
            <div className="flex flex-wrap items-center gap-3 p-4">
              <Button variant="primary"><Plus /> New request</Button>
              <Button>Secondary</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="brand">Brand</Button>
              <Button variant="danger"><Trash2 /> Delete</Button>
              <Button variant="link">Link</Button>
              <Button variant="primary" loading>Saving</Button>
              <Button disabled>Disabled</Button>
              <Tooltip content="Export as CSV"><Button size="icon" variant="ghost" aria-label="Export"><Download /></Button></Tooltip>
              <Button size="sm">Small</Button>
              <Button size="lg" variant="primary">Large</Button>
            </div>
          </Panel>

          <Panel title="Form controls" description="Label, hint, inline validation, required marker">
            <div className="grid gap-5 p-4 md:grid-cols-2">
              <FormField label="Request title" htmlFor="ds-title" hint="Shown to approvers in their inbox." required>
                <Input placeholder="e.g. Site fencing — Building B" />
              </FormField>
              <FormField label="Amount (SAR)" htmlFor="ds-amount" error="Amount must be greater than zero." required>
                <Input inputMode="decimal" defaultValue="0" />
              </FormField>
              <FormField label="Budget category" htmlFor="ds-cat">
                <Select value={plan} onValueChange={setPlan} options={[{ value: "standard", label: "Construction CAPEX" }, { value: "mkt", label: "Marketing" }, { value: "it", label: "IT" }]} />
              </FormField>
              <FormField label="Disabled field" htmlFor="ds-disabled"><Input disabled value="Read-only value" readOnly /></FormField>
              <FormField label="Justification" htmlFor="ds-just" className="md:col-span-2"><Textarea placeholder="Why is this purchase needed?" /></FormField>
              <div className="flex items-center gap-2 md:col-span-2"><Checkbox id="ds-check" defaultChecked /><Label htmlFor="ds-check">Notify the requester when approved</Label></div>
              <FormAlert className="md:col-span-2" message="This request exceeds the available budget. It will be routed to Finance and the Executive for approval." />
            </div>
            <div className="flex justify-end gap-2 border-t border-border-subtle bg-surface-subtle px-4 py-3">
              <Button>Cancel</Button>
              <Button variant="primary" onClick={() => toast.success("Saved", { description: "Sample toast — nothing was stored." })}>Save draft</Button>
            </div>
          </Panel>

          <Panel title="Badges & status" description="Dot + label, never colour alone">
            <div className="flex flex-wrap items-center gap-2 p-4">
              {["draft", "pending_approval", "approved", "rejected", "running", "failed", "available", "reserved", "sold"].map((s) => <StatusBadge key={s} status={s} />)}
              <AiBadge />
              <Chip>Finance Manager</Chip>
            </div>
          </Panel>

          <Panel title="Dialogs & feedback">
            <div className="flex flex-wrap gap-3 p-4">
              <Button variant="danger" onClick={() => setConfirmOpen(true)}>Open confirm dialog</Button>
              <Button onClick={() => toast("Workflow retried", { description: "Execution WF-1042 is running again (sample)." })}>Info toast</Button>
              <Button onClick={() => toast.error("Approval failed", { description: "The budget changed. Reload and try again (sample)." })}>Error toast</Button>
            </div>
          </Panel>
          <ConfirmDialog open={confirmOpen} onOpenChange={setConfirmOpen} tone="danger" title="Reject PR-00012 for SAR 84,500?"
            description="The requester will be notified. This cannot be undone. (Sample — nothing happens.)" confirmLabel="Reject request"
            onConfirm={() => { setConfirmOpen(false); toast.success("Sample action confirmed"); }} />
        </TabsContent>

        {/* ---------------------------------------------------------------- Data display */}
        <TabsContent value="data" className="space-y-6">
          <div>
            <h2 className="mb-3 text-body font-semibold">KPI cards <SampleTag /></h2>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard label="Budget used" value="68.4%" delta={{ value: 4.2, label: "vs last month", goodDirection: "down" }} sparkline={[52, 55, 58, 61, 64, 68]} />
              <KpiCard label="Open approvals" value="14" delta={{ value: -12.5, label: "vs last week", goodDirection: "down" }} />
              <KpiCard label="Units reserved" value="37" delta={{ value: 8.1, label: "vs last month" }} hint="of 120" />
              <KpiCard label="Loading state" value="" loading />
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Committed vs actual spend" subtitle="SAR thousands · last 5 months (sample)" data={SAMPLE_CHART} xKey="month"
              series={[{ key: "committed", label: "Committed", slot: 1 }, { key: "actual", label: "Actual", slot: 2 }]} formatValue={(v) => `${v}k`} />
            <ChartCard title="Actual spend trend" subtitle="SAR thousands (sample)" type="line" data={SAMPLE_CHART} xKey="month"
              series={[{ key: "actual", label: "Actual", slot: 3 }]} formatValue={(v) => `${v}k`} />
          </div>

          <Panel title="Meters" description="Utilisation tone shifts at 80% and 100%">
            <div className="grid gap-4 p-4 sm:grid-cols-3">
              {[42, 86, 104].map((v) => <div key={v} className="space-y-1.5"><div className="flex justify-between text-small"><span className="text-fg-secondary">Budget</span><span className="tabular font-medium">{v}%</span></div><Meter value={v} label="Budget utilisation" /></div>)}
            </div>
          </Panel>

          <div>
            <h2 className="mb-3 text-body font-semibold">Data table <SampleTag /></h2>
            <DataTable ariaLabel="Sample purchase requests" columns={columns} page={samplePage} isLoading={false} state={tableState}
              searchPlaceholder="Search requests" getRowId={(r) => r.id}
              filters={<Select aria-label="Status" className="h-8 w-40" value="all" onValueChange={() => undefined} options={[{ value: "all", label: "All statuses" }]} />}
              mobileRow={(r) => (
                <div className="flex items-start justify-between gap-3">
                  <div><p className="tabular text-small text-fg-muted">{r.code}</p><p className="font-medium">{r.title}</p><StatusBadge status={r.status} className="mt-1" /></div>
                  <MoneyText value={r.amount} className="font-medium" />
                </div>
              )} />
          </div>
        </TabsContent>

        {/* ---------------------------------------------------------------- States */}
        <TabsContent value="states" className="grid gap-4 lg:grid-cols-2">
          <Panel title="Empty"><EmptyState title="No purchase requests yet" description="Create a request to start the approval flow." action={<Button variant="primary" size="sm"><Plus /> New request</Button>} /></Panel>
          <Panel title="Filtered empty"><EmptyState filtered onClearFilters={() => toast("Filters cleared (sample)")} /></Panel>
          <Panel title="Error"><ErrorState error={new ApiError(503, { code: "service_unavailable", message: "The finance service didn't respond.", request_id: "a1b2c3d4e5f6" })} onRetry={() => toast("Retrying (sample)")} /></Panel>
          <Panel title="Permission denied"><PermissionState /></Panel>
          <Panel title="Loading — table"><TableSkeleton rows={4} /></Panel>
          <Panel title="Loading — list"><ListSkeleton rows={3} /></Panel>
        </TabsContent>
      </Tabs>
    </>
  );
}
