import { CalendarCheck, Send, UserPlus } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { MoneyText } from "@/components/system/data-display";
import { FormAlert, FormField } from "@/components/system/forms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { Checkbox, Label } from "@/components/ui/primitives";
import { useProjects, useUnits } from "@/features/realestate/api";
import { bedroomsLabel } from "@/features/realestate/logic";
import { ApiError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import { useCreateLead, useLeadMutations, useReservationMutations, useSalesUsers, type LeadDetail, type Stage } from "./api";
import { ACTIVITY_TYPES, SOURCES, TIMELINES, fromLocalInput, stageLabel, stageNeedsReason, toLocalInput } from "./crm-logic";

const errText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export function StageDialog({ lead, target, onClose }: { lead: LeadDetail; target: Stage; onClose: () => void }) {
  const { stage } = useLeadMutations(lead.id);
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const needsReason = stageNeedsReason(target);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (needsReason && reason.trim().length < 3) return setError("Give a reason (at least 3 characters).");
    stage.mutate({ stage: target, reason: reason.trim() || null }, {
      onSuccess: () => { toast.success(`${lead.code} moved to ${stageLabel(target)}`); onClose(); },
      onError: (err) => setError(errText(err, "Couldn't change the stage")),
    });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader title={`Move ${lead.code} to ${stageLabel(target)}?`}
          description={lead.stage === "lost" ? "This reopens the lead and schedules a follow-up in 48 hours." : `From ${stageLabel(lead.stage)}. Recorded in the timeline.`} />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormField label={needsReason ? "Reason" : "Note (optional)"} htmlFor="stage-reason" error={error ?? undefined} required={needsReason}>
            <Textarea id="stage-reason" rows={3} maxLength={500} value={reason} onChange={(e) => { setReason(e.target.value); setError(null); }}
              placeholder={target === "lost" ? "Why was the lead lost?" : target === "won" ? "What was agreed?" : undefined} />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant={target === "lost" ? "danger" : "primary"} loading={stage.isPending}>Move to {stageLabel(target)}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ActivityForm({ lead }: { lead: LeadDetail }) {
  const { activity } = useLeadMutations(lead.id);
  const [type, setType] = React.useState("call");
  const [body, setBody] = React.useState("");
  const [followUp, setFollowUp] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (body.trim().length < 2) return setError("Describe the activity.");
    activity.mutate({ type, body: body.trim(), next_follow_up_at: fromLocalInput(followUp) }, {
      onSuccess: () => { toast.success("Activity logged"); setBody(""); setFollowUp(""); setError(null); },
      onError: (err) => setError(errText(err, "Couldn't log the activity")),
    });
  };
  return (
    <form onSubmit={submit} noValidate className="space-y-3 border-b border-border-subtle p-4" aria-label="Log an activity">
      <FormAlert message={error} />
      <div className="grid gap-3 sm:grid-cols-[150px_minmax(0,1fr)]">
        <Select aria-label="Activity type" value={type} onValueChange={setType} options={ACTIVITY_TYPES} />
        <Textarea aria-label="What happened?" rows={2} maxLength={1000} value={body} onChange={(e) => { setBody(e.target.value); setError(null); }} placeholder="What happened? (no sensitive data)" />
      </div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <FormField label="Next follow-up (optional)" htmlFor="activity-follow" className="sm:w-64">
          <Input id="activity-follow" type="datetime-local" value={followUp} onChange={(e) => setFollowUp(e.target.value)} />
        </FormField>
        <Button type="submit" variant="primary" loading={activity.isPending}><Send /> Log activity</Button>
      </div>
    </form>
  );
}

export function FollowUpDialog({ lead, onClose }: { lead: LeadDetail; onClose: () => void }) {
  const { update } = useLeadMutations(lead.id);
  const [value, setValue] = React.useState(toLocalInput(lead.next_follow_up_at));
  const [error, setError] = React.useState<string | null>(null);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const iso = fromLocalInput(value);
    if (!iso) return setError("Pick a date and time.");
    update.mutate({ next_follow_up_at: iso }, {
      onSuccess: () => { toast.success(`Follow-up set for ${formatDateTime(iso)}`); onClose(); },
      onError: (err) => setError(errText(err, "Couldn't save the follow-up")),
    });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader title="Schedule the next follow-up" description="Overdue follow-ups are escalated to the sales manager." />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormField label="Follow up by" htmlFor="follow-up" error={error ?? undefined} required>
            <Input id="follow-up" type="datetime-local" value={value} onChange={(e) => { setValue(e.target.value); setError(null); }} />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={update.isPending}><CalendarCheck /> Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ReassignDialog({ lead, onClose }: { lead: LeadDetail; onClose: () => void }) {
  const { assign } = useLeadMutations(lead.id);
  const users = useSalesUsers(true);
  const [owner, setOwner] = React.useState<string | undefined>(undefined);
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const options = (users.data ?? []).filter((u) => u.id !== lead.owner?.id).map((u) => ({ value: u.id, label: u.full_name }));
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!owner) return setError("Choose the new owner.");
    assign.mutate({ owner_user_id: owner, reason: reason.trim() || null }, {
      onSuccess: (d) => { toast.success(`${lead.code} reassigned to ${d.owner?.full_name}`); onClose(); },
      onError: (err) => setError(errText(err, "Couldn't reassign the lead")),
    });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader title={`Reassign ${lead.code}`} description={`Current owner: ${lead.owner?.full_name ?? "unassigned"}. The new owner is notified.`} />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={error} />
          <FormField label="New owner" htmlFor="reassign-owner" required>
            <Select id="reassign-owner" value={owner} onValueChange={(v) => { setOwner(v); setError(null); }} options={options}
              placeholder={users.isPending ? "Loading…" : options.length ? "Choose a sales consultant" : "No other sales users"} disabled={!options.length} />
          </FormField>
          <FormField label="Reason (optional)" htmlFor="reassign-reason">
            <Input id="reassign-reason" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={assign.isPending}><UserPlus /> Reassign</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ReserveDialog({ lead, onClose }: { lead: LeadDetail; onClose: () => void }) {
  const { create } = useReservationMutations();
  const projects = useProjects();
  const [projectId, setProjectId] = React.useState<string | undefined>(lead.project?.id);
  const effectiveProject = projectId ?? (projects.data?.items.length === 1 ? projects.data.items[0]?.id : undefined);
  const units = useUnits({ project_id: effectiveProject, status: "available", page_size: 100, sort: "list_price" }, Boolean(effectiveProject));
  const [unitId, setUnitId] = React.useState<string | undefined>(lead.interested_unit?.id);
  const [hours, setHours] = React.useState("72");
  const [deposit, setDeposit] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const unitOptions = (units.data?.items ?? []).map((u) => ({
    value: u.id, label: `${u.building.code}-${u.unit_number} · ${bedroomsLabel(u.bedrooms)} · SAR ${Number(u.list_price).toLocaleString("en-US")}`,
  }));
  const selected = units.data?.items.find((u) => u.id === unitId);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const h = Number(hours);
    if (!unitId || !selected) return setError("Choose an available unit.");
    if (!Number.isInteger(h) || h < 1 || h > 720) return setError("Hold the unit for 1 to 720 hours.");
    const dep = deposit.replace(/[^\d.]/g, "");
    if (deposit && !/^\d+(\.\d{1,2})?$/.test(dep)) return setError("Enter the deposit as an amount, e.g. 25000.");
    create.mutate({ lead_id: lead.id, unit_id: unitId, hours: h, deposit_amount: dep || null, notes: notes.trim() || null }, {
      onSuccess: (r) => { toast.success(`${r.code}: ${r.unit.code} reserved for ${lead.code}`); onClose(); },
      onError: (err) => setError(errText(err, "Couldn't reserve the unit")),
    });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader title={`Reserve a unit for ${lead.code}`}
          description="The unit is held exclusively until the reservation expires, is cancelled or converted to a sale." />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={error} />
          {!lead.project && (
            <FormField label="Project" htmlFor="reserve-project" required>
              <Select id="reserve-project" value={effectiveProject} onValueChange={(v) => { setProjectId(v); setUnitId(undefined); }}
                options={(projects.data?.items ?? []).map((p) => ({ value: p.id, label: p.name }))} placeholder="Choose a project" />
            </FormField>
          )}
          <FormField label="Available unit" htmlFor="reserve-unit" required hint={units.data && !unitOptions.length ? "No units are available right now." : undefined}>
            <Select id="reserve-unit" value={unitId} onValueChange={(v) => { setUnitId(v); setError(null); }} options={unitOptions}
              placeholder={units.isFetching ? "Loading units…" : "Choose a unit"} disabled={!unitOptions.length} />
          </FormField>
          {selected && (
            <p className="rounded-[var(--radius-control)] border border-border bg-surface-subtle px-3 py-2 text-small text-fg-secondary">
              {selected.project.name} · floor {selected.floor} · {Number(selected.area_sqm).toLocaleString("en-US")} m² · <MoneyText value={selected.list_price} className="font-medium text-fg" />
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Hold for (hours)" htmlFor="reserve-hours" hint="Default 72 hours" required>
              <Input id="reserve-hours" type="number" min={1} max={720} value={hours} onChange={(e) => setHours(e.target.value)} />
            </FormField>
            <FormField label="Deposit (SAR, optional)" htmlFor="reserve-deposit" hint="Informational only — not posted to any ledger">
              <Input id="reserve-deposit" inputMode="decimal" value={deposit} onChange={(e) => setDeposit(e.target.value)} placeholder="e.g. 25000" />
            </FormField>
          </div>
          <FormField label="Notes (optional)" htmlFor="reserve-notes">
            <Textarea id="reserve-notes" rows={2} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={create.isPending}><CalendarCheck /> Reserve unit</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function NewLeadDialog({ onClose }: { onClose: () => void }) {
  const create = useCreateLead();
  const projects = useProjects();
  const navigate = useNavigate();
  const [f, setF] = React.useState({ full_name: "", phone: "", email: "", source: "walk_in", interest: "", budget_min: "", budget_max: "", bedrooms: "", timeline: "", project_id: "" });
  const [consent, setConsent] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }));
  const money = (v: string) => v.replace(/[^\d.]/g, "") || null;
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (f.full_name.trim().length < 2) return setError("Enter the lead's name.");
    if (!f.phone.trim() && !f.email.trim()) return setError("Provide a phone number or an email address.");
    create.mutate({
      full_name: f.full_name.trim(), phone: f.phone.trim() || null, email: f.email.trim() || null, source: f.source,
      interest: f.interest.trim() || null, budget_min: money(f.budget_min), budget_max: money(f.budget_max),
      bedrooms_wanted: f.bedrooms ? Number(f.bedrooms) : null, timeline: f.timeline || null, project_id: f.project_id || null, consent,
    }, {
      onSuccess: (lead) => { toast.success(`${lead.code} registered`, { description: "It is scored and assigned automatically." }); onClose(); navigate(`/crm/leads/${lead.id}`); },
      onError: (err) => setError(errText(err, "Couldn't register the lead")),
    });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] max-w-xl overflow-y-auto">
        <DialogHeader title="Register a lead" description="Scoring and round-robin assignment run automatically after saving." />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={error} />
          <FormField label="Full name" htmlFor="lead-name" required><Input id="lead-name" maxLength={150} value={f.full_name} onChange={(e) => set("full_name")(e.target.value)} /></FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Phone" htmlFor="lead-phone"><Input id="lead-phone" type="tel" maxLength={40} value={f.phone} onChange={(e) => set("phone")(e.target.value)} /></FormField>
            <FormField label="Email" htmlFor="lead-email"><Input id="lead-email" type="email" value={f.email} onChange={(e) => set("email")(e.target.value)} /></FormField>
            <FormField label="Source" htmlFor="lead-source" required><Select id="lead-source" value={f.source} onValueChange={set("source")} options={SOURCES} /></FormField>
            <FormField label="Project" htmlFor="lead-project">
              <Select id="lead-project" value={f.project_id || undefined} onValueChange={set("project_id")} placeholder="Any project"
                options={(projects.data?.items ?? []).map((p) => ({ value: p.id, label: p.name }))} />
            </FormField>
            <FormField label="Budget from (SAR)" htmlFor="lead-bmin"><Input id="lead-bmin" inputMode="decimal" value={f.budget_min} onChange={(e) => set("budget_min")(e.target.value)} /></FormField>
            <FormField label="Budget up to (SAR)" htmlFor="lead-bmax"><Input id="lead-bmax" inputMode="decimal" value={f.budget_max} onChange={(e) => set("budget_max")(e.target.value)} /></FormField>
            <FormField label="Bedrooms" htmlFor="lead-beds">
              <Select id="lead-beds" value={f.bedrooms || undefined} onValueChange={set("bedrooms")} placeholder="Any"
                options={[0, 1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: n === 0 ? "Studio" : `${n} bedrooms` }))} />
            </FormField>
            <FormField label="Timeline" htmlFor="lead-timeline"><Select id="lead-timeline" value={f.timeline || undefined} onValueChange={set("timeline")} options={TIMELINES} placeholder="Unknown" /></FormField>
          </div>
          <FormField label="Interest" htmlFor="lead-interest"><Input id="lead-interest" maxLength={300} value={f.interest} onChange={(e) => set("interest")(e.target.value)} placeholder="e.g. 2-bedroom with park view" /></FormField>
          <div className="flex items-center gap-2">
            <Checkbox id="lead-consent" checked={consent} onCheckedChange={(v) => setConsent(v === true)} />
            <Label htmlFor="lead-consent">The lead agreed to be contacted</Label>
          </div>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={create.isPending}><UserPlus /> Register lead</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
