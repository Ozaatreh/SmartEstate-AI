/**
 * Inventory management dialogs (realestate.inventory.manage). They are only rendered for users who hold the
 * permission; the API enforces it again and owns every business rule (codes, floors, shares, unit status).
 */
import { Lock, Save } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FormAlert, FormField } from "@/components/system/forms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { Checkbox, Label } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api-client";
import {
  useProject, useProjects, useSaveBuilding, useSavePlan, useSaveProject, useSaveUnit,
  type Building, type MarketingStatus, type PaymentPlan, type ProjectDetail, type UnitDetail,
} from "./api";
import {
  CODE_PATTERN, FREQUENCIES, LOCKED_WHEN_COMMITTED, PROJECT_STATUSES, UNIT_TYPES, changedFields, isPositiveAmount,
  coordinateErrors, mediaError, mediaPayload, mediaRows, parseAmenities, planShareError, unitIsCommitted,
} from "./logic";
import { MediaEditor } from "./media-editor";

const MARKETING_OPTIONS = [
  { value: "unreviewed", label: "Not reviewed — kept out of marketing" },
  { value: "cleared", label: "Cleared for marketing" },
  { value: "excluded", label: "Excluded from marketing (e.g. test plan)" },
];

type Errors = Record<string, string>;

/** Maps an API error onto field messages + a form-level message. */
function useServerErrors() {
  const [errors, setErrors] = React.useState<Errors>({});
  const [alert, setAlert] = React.useState<string | null>(null);
  const apply = (err: unknown) => {
    if (err instanceof ApiError) {
      const fields = err.fieldErrors;
      setErrors(fields);
      setAlert(Object.keys(fields).length && err.status === 422 ? "Fix the highlighted fields." : err.message);
    } else {
      setAlert("Something went wrong. Try again.");
    }
  };
  const reset = (client: Errors = {}) => { setErrors(client); setAlert(Object.keys(client).length ? "Fix the highlighted fields." : null); };
  return { errors, alert, apply, reset, clear: (k: string) => setErrors((e) => ({ ...e, [k]: "" })) };
}

const scroll = "max-h-[90dvh] overflow-y-auto";

// ============================================================================ projects
export function ProjectFormDialog({ project, onClose }: { project?: ProjectDetail; onClose: () => void }) {
  const save = useSaveProject(project?.id);
  const navigate = useNavigate();
  const s = useServerErrors();
  const [f, setF] = React.useState({
    code: project?.code ?? "",
    name: project?.name ?? "",
    city: project?.city ?? "",
    district: project?.district ?? "",
    status: project?.status ?? "planning",
    launch_date: project?.launch_date ?? "",
    handover_date: project?.handover_date ?? "",
    description: project?.description ?? "",
    amenities: (project?.amenities ?? []).join("\n"),
    address: project?.address ?? "",
    country: project?.country ?? "",
    latitude: project?.latitude ? String(Number(project.latitude)) : "",
    longitude: project?.longitude ? String(Number(project.longitude)) : "",
    illustrative_label: project?.illustrative_label ?? "",
    illustrative_latitude: project?.illustrative_latitude ? String(Number(project.illustrative_latitude)) : "",
    illustrative_longitude: project?.illustrative_longitude ? String(Number(project.illustrative_longitude)) : "",
    illustrative_source: project?.illustrative_source ?? "",
  });
  const [media, setMedia] = React.useState(() => mediaRows(project?.media));
  const [published, setPublished] = React.useState(project?.is_published ?? false);
  const [verified, setVerified] = React.useState(project?.location_verified ?? false);
  const demo = project?.is_demo_data ?? false;
  const set = (k: keyof typeof f) => (v: string) => { setF((x) => ({ ...x, [k]: v })); s.clear(k); };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Errors = {};
    if (!project && (f.code.trim().length < 2 || !CODE_PATTERN.test(f.code.trim()))) errs.code = "2–20 letters, digits or dashes.";
    if (f.name.trim().length < 2) errs.name = "Enter the project name.";
    if (f.city.trim().length < 2) errs.city = "Enter the city.";
    if (f.launch_date && f.handover_date && f.handover_date < f.launch_date) errs.handover_date = "Handover cannot be before launch.";
    const mediaProblem = mediaError(media);
    if (mediaProblem) errs.media = mediaProblem;
    Object.assign(errs, coordinateErrors(f.latitude, f.longitude, verified && !demo));
    const ill = coordinateErrors(f.illustrative_latitude, f.illustrative_longitude, false);
    if (ill.latitude) errs.illustrative_latitude = ill.latitude;
    if (ill.longitude) errs.illustrative_longitude = ill.longitude;
    if ((f.illustrative_latitude.trim() || f.illustrative_longitude.trim()) && !f.illustrative_label.trim())
      errs.illustrative_label = "Name the reference place, e.g. a landmark.";
    if (verified && !demo && f.illustrative_latitude.trim())
      errs.illustrative_latitude = "Remove the illustrative point: a verified location is shown instead.";
    if (Object.keys(errs).length) return s.reset(errs);
    s.reset();
    save.mutate({
      ...(project ? {} : { code: f.code.trim().toUpperCase() }),
      name: f.name.trim(), city: f.city.trim(), district: f.district.trim() || null, status: f.status,
      launch_date: f.launch_date || null, handover_date: f.handover_date || null, description: f.description.trim() || null,
      amenities: parseAmenities(f.amenities), media: mediaPayload(media), is_published: published,
      address: f.address.trim() || null, country: f.country.trim() || null,
      latitude: f.latitude.trim() || null, longitude: f.longitude.trim() || null, location_verified: verified && !demo,
      illustrative_label: f.illustrative_label.trim() || null, illustrative_source: f.illustrative_source.trim() || null,
      illustrative_latitude: f.illustrative_latitude.trim() || null, illustrative_longitude: f.illustrative_longitude.trim() || null,
    }, {
      onSuccess: (p) => { toast.success(project ? `${p.code} updated` : `${p.code} created`); onClose(); if (!project) navigate(`/realestate/projects/${p.id}`); },
      onError: s.apply,
    });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className={`${scroll} max-w-xl`}>
        <DialogHeader title={project ? `Edit ${project.code}` : "New project"} description="Mark demo content as fictional in the description." />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={s.alert} />
          <div className="grid gap-4 sm:grid-cols-2">
            {project ? (
              <FormField label="Code" htmlFor="p-code" hint="Codes can't be changed"><Input value={project.code} disabled /></FormField>
            ) : (
              <FormField label="Code" htmlFor="p-code" required error={s.errors.code} hint="e.g. NOVA-2">
                <Input maxLength={20} value={f.code} onChange={(e) => set("code")(e.target.value)} />
              </FormField>
            )}
            <FormField label="Status" htmlFor="p-status" required><Select value={f.status} onValueChange={set("status")} options={PROJECT_STATUSES} /></FormField>
          </div>
          <FormField label="Name" htmlFor="p-name" required error={s.errors.name}><Input maxLength={150} value={f.name} onChange={(e) => set("name")(e.target.value)} /></FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="City" htmlFor="p-city" required error={s.errors.city}><Input maxLength={80} value={f.city} onChange={(e) => set("city")(e.target.value)} /></FormField>
            <FormField label="District" htmlFor="p-district" error={s.errors.district}><Input maxLength={80} value={f.district} onChange={(e) => set("district")(e.target.value)} /></FormField>
            <FormField label="Launch date" htmlFor="p-launch" error={s.errors.launch_date}><Input type="date" value={f.launch_date} onChange={(e) => set("launch_date")(e.target.value)} /></FormField>
            <FormField label="Handover date" htmlFor="p-handover" error={s.errors.handover_date}><Input type="date" value={f.handover_date} onChange={(e) => set("handover_date")(e.target.value)} /></FormField>
          </div>
          <fieldset className="space-y-3 rounded-[var(--radius-control)] border border-border p-3">
            <legend className="px-1 text-small font-medium">Location (maps)</legend>
            <FormField label="Address" htmlFor="p-address" error={s.errors.address}><Input maxLength={250} value={f.address} onChange={(e) => set("address")(e.target.value)} /></FormField>
            <div className="grid gap-4 sm:grid-cols-3">
              <FormField label="Country" htmlFor="p-country" error={s.errors.country}><Input maxLength={80} value={f.country} onChange={(e) => set("country")(e.target.value)} /></FormField>
              <FormField label="Latitude" htmlFor="p-lat" hint="-90 to 90" error={s.errors.latitude}><Input inputMode="decimal" placeholder="e.g. 24.774265" value={f.latitude} onChange={(e) => set("latitude")(e.target.value)} /></FormField>
              <FormField label="Longitude" htmlFor="p-lng" hint="-180 to 180" error={s.errors.longitude}><Input inputMode="decimal" placeholder="e.g. 46.738586" value={f.longitude} onChange={(e) => set("longitude")(e.target.value)} /></FormField>
            </div>
            <div className="flex items-start gap-2">
              <Checkbox id="p-verified" checked={verified && !demo} disabled={demo} onCheckedChange={(v) => setVerified(v === true)} />
              <div><Label htmlFor="p-verified">Location verified — show the map pin and directions on the website</Label>
                <p className="text-caption text-fg-muted">{demo
                  ? "Fictional demo project: its location can't be verified, so the website shows only the city and district."
                  : "Confirm the coordinates against an official source first. Changing them later clears this until confirmed again."}</p></div>
            </div>
          </fieldset>
          <fieldset className="space-y-3 rounded-[var(--radius-control)] border border-border p-3">
            <legend className="px-1 text-small font-medium">Illustrative map point (optional)</legend>
            <p className="text-caption text-fg-muted">
              A reference place (e.g. a landmark) shown on the website map when the property's own location isn't verified.
              It is labelled "Illustrative Location — Not the Actual Property Location", is never shown as the address,
              and its directions lead to the reference place.
            </p>
            <FormField label="Reference place" htmlFor="p-ill-label" hint="Shown on the website, e.g. Kingdom Centre, Riyadh" error={s.errors.illustrative_label}>
              <Input maxLength={120} value={f.illustrative_label} onChange={(e) => set("illustrative_label")(e.target.value)} /></FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Reference latitude" htmlFor="p-ill-lat" hint="-90 to 90" error={s.errors.illustrative_latitude}>
                <Input inputMode="decimal" value={f.illustrative_latitude} onChange={(e) => set("illustrative_latitude")(e.target.value)} /></FormField>
              <FormField label="Reference longitude" htmlFor="p-ill-lng" hint="-180 to 180" error={s.errors.illustrative_longitude}>
                <Input inputMode="decimal" value={f.illustrative_longitude} onChange={(e) => set("illustrative_longitude")(e.target.value)} /></FormField>
            </div>
            <FormField label="Coordinate source" htmlFor="p-ill-source" hint="Internal: where the coordinates come from" error={s.errors.illustrative_source}>
              <Input maxLength={250} value={f.illustrative_source} onChange={(e) => set("illustrative_source")(e.target.value)} /></FormField>
          </fieldset>
          <FormField label="Description" htmlFor="p-desc" error={s.errors.description}><Textarea rows={3} maxLength={4000} value={f.description} onChange={(e) => set("description")(e.target.value)} /></FormField>
          <FormField label="Amenities" htmlFor="p-amen" hint="One per line" error={s.errors.amenities}><Textarea rows={3} value={f.amenities} onChange={(e) => set("amenities")(e.target.value)} /></FormField>
          <MediaEditor rows={media} projectId={project?.id} onChange={(rows) => { setMedia(rows); s.clear("media"); }} error={s.errors.media} />
          <div className="flex items-start gap-2">
            <Checkbox id="p-published" checked={published} onCheckedChange={(v) => setPublished(v === true)} />
            <div><Label htmlFor="p-published">Published on the marketing website</Label>
              <p className="text-caption text-fg-muted">Visitors and the public assistant see this project and its public units.</p></div>
          </div>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={save.isPending}><Save /> {project ? "Save changes" : "Create project"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================ buildings
export function BuildingFormDialog({ projectId, building, onClose }: { projectId: string; building?: Building; onClose: () => void }) {
  const save = useSaveBuilding(projectId, building?.id);
  const s = useServerErrors();
  const [code, setCode] = React.useState(building?.code ?? "");
  const [name, setName] = React.useState(building?.name ?? "");
  const [floors, setFloors] = React.useState(String(building?.floors ?? ""));
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Errors = {};
    if (!building && (!code.trim() || !CODE_PATTERN.test(code.trim()))) errs.code = "Letters, digits or dashes.";
    if (name.trim().length < 2) errs.name = "Enter the building name.";
    const n = Number(floors);
    if (!Number.isInteger(n) || n < 1 || n > 200) errs.floors = "Between 1 and 200 floors.";
    if (Object.keys(errs).length) return s.reset(errs);
    s.reset();
    save.mutate({ code: code.trim().toUpperCase(), name: name.trim(), floors: n }, {
      onSuccess: (b) => { toast.success(building ? `${b.code} updated` : `${b.code} added`); onClose(); },
      onError: s.apply,
    });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader title={building ? `Edit ${building.code}` : "Add building"}
          description={building ? "Floors can't go below the highest floor that has units." : undefined} />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={s.alert} />
          <div className="grid gap-4 sm:grid-cols-[120px_minmax(0,1fr)]">
            <FormField label="Code" htmlFor="b-code" required={!building} error={s.errors.code}>
              <Input maxLength={20} value={code} disabled={Boolean(building)} onChange={(e) => { setCode(e.target.value); s.clear("code"); }} />
            </FormField>
            <FormField label="Name" htmlFor="b-name" required error={s.errors.name}><Input maxLength={120} value={name} onChange={(e) => { setName(e.target.value); s.clear("name"); }} /></FormField>
          </div>
          <FormField label="Floors" htmlFor="b-floors" required error={s.errors.floors}>
            <Input type="number" min={1} max={200} value={floors} onChange={(e) => { setFloors(e.target.value); s.clear("floors"); }} />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={save.isPending}><Save /> {building ? "Save changes" : "Add building"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================ payment plans
export function PlanFormDialog({ projectId, plan, onClose }: { projectId: string; plan?: PaymentPlan; onClose: () => void }) {
  const save = useSavePlan(projectId, plan?.id);
  const s = useServerErrors();
  const num = (v: string | undefined, d: string) => (v === undefined ? d : String(Number(v)));
  const [f, setF] = React.useState({
    name: plan?.name ?? "",
    down: num(plan?.down_payment_pct, "10"),
    installments: String(plan?.installments ?? 36),
    frequency: plan?.installment_frequency ?? "monthly",
    handover: num(plan?.handover_pct, "0"),
    description: plan?.description ?? "",
  });
  const [active, setActive] = React.useState(plan?.is_active ?? true);
  const [marketing, setMarketing] = React.useState<MarketingStatus>(plan?.marketing_status ?? "unreviewed");
  const set = (k: keyof typeof f) => (v: string) => { setF((x) => ({ ...x, [k]: v })); s.reset(); };
  const shareError = planShareError(f.down, f.handover, f.installments);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Errors = {};
    if (f.name.trim().length < 2) errs.name = "Enter the plan name.";
    if (shareError) errs.shares = shareError;
    if (Object.keys(errs).length) return s.reset(errs);
    save.mutate({
      name: f.name.trim(), down_payment_pct: f.down, installments: Number(f.installments), installment_frequency: f.frequency,
      handover_pct: f.handover, description: f.description.trim() || null, is_active: active,
      marketing_status: marketing,
    }, {
      onSuccess: (p) => { toast.success(plan ? `${p.name} updated` : `${p.name} added`); onClose(); },
      onError: s.apply,
    });
  };
  const middle = Math.max(0, 100 - (Number(f.down) || 0) - (Number(f.handover) || 0));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className={scroll}>
        <DialogHeader title={plan ? `Edit ${plan.name}` : "Add payment plan"} description="Shares are percentages of the unit's list price." />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={s.alert} />
          <FormField label="Name" htmlFor="pl-name" required error={s.errors.name}><Input maxLength={100} value={f.name} onChange={(e) => set("name")(e.target.value)} /></FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Down payment (%)" htmlFor="pl-down" required error={s.errors.down_payment_pct}><Input inputMode="decimal" value={f.down} onChange={(e) => set("down")(e.target.value)} /></FormField>
            <FormField label="On handover (%)" htmlFor="pl-handover" required error={s.errors.handover_pct}><Input inputMode="decimal" value={f.handover} onChange={(e) => set("handover")(e.target.value)} /></FormField>
            <FormField label="Installments" htmlFor="pl-n" required error={s.errors.installments}><Input type="number" min={0} max={240} value={f.installments} onChange={(e) => set("installments")(e.target.value)} /></FormField>
            <FormField label="Frequency" htmlFor="pl-freq" required><Select value={f.frequency} onValueChange={set("frequency")} options={FREQUENCIES} /></FormField>
          </div>
          <p className={shareError ? "text-small text-danger" : "text-small text-fg-secondary"} role={shareError ? "alert" : undefined}>
            {s.errors.shares || shareError || `${middle}% is paid in installments.`}
          </p>
          <FormField label="Description" htmlFor="pl-desc"><Textarea rows={2} maxLength={1000} value={f.description} onChange={(e) => set("description")(e.target.value)} /></FormField>
          <div className="flex items-center gap-2">
            <Checkbox id="pl-active" checked={active} onCheckedChange={(v) => setActive(v === true)} />
            <Label htmlFor="pl-active">Active (offered on unit pages)</Label>
          </div>
          <FormField label="Marketing use" htmlFor="pl-marketing" hint="Only plans cleared for marketing appear on the website, in the assistant, brochures and posters. Leave test plans not reviewed or excluded.">
            <Select value={marketing} onValueChange={(v) => setMarketing(v as MarketingStatus)} options={MARKETING_OPTIONS} />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={save.isPending} disabled={Boolean(shareError)}><Save /> {plan ? "Save changes" : "Add plan"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================ units
export function UnitFormDialog({ unit, projectId, onClose }: { unit?: UnitDetail; projectId?: string; onClose: () => void }) {
  const save = useSaveUnit(unit?.id);
  const navigate = useNavigate();
  const s = useServerErrors();
  const projects = useProjects();
  const [project, setProject] = React.useState<string | undefined>(unit?.project.id ?? projectId);
  const detail = useProject(unit ? undefined : project);
  const committed = unit ? unitIsCommitted(unit.status) : false;
  const locked = (k: string) => committed && (LOCKED_WHEN_COMMITTED as readonly string[]).includes(k);
  const initial = {
    building_id: unit?.building.id ?? "",
    unit_number: unit?.unit_number ?? "",
    unit_type: unit?.unit_type ?? "apartment",
    bedrooms: String(unit?.bedrooms ?? 2),
    bathrooms: String(unit?.bathrooms ?? 2),
    floor: String(unit?.floor ?? 1),
    area_sqm: unit?.area_sqm ?? "",
    view: unit?.view ?? "",
    list_price: unit?.list_price ?? "",
    notes: unit?.notes ?? "",
  };
  const [f, setF] = React.useState(initial);
  const [publicListing, setPublic] = React.useState(unit?.is_public ?? true);
  const [blocked, setBlocked] = React.useState(false);
  const set = (k: keyof typeof f) => (v: string) => { setF((x) => ({ ...x, [k]: v })); s.clear(k); };
  const building = detail.data?.buildings.find((b) => b.id === f.building_id);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Errors = {};
    if (!unit) {
      if (!f.building_id) errs.building_id = "Choose a building.";
      if (!f.unit_number.trim() || !CODE_PATTERN.test(f.unit_number.trim())) errs.unit_number = "Letters, digits or dashes.";
    }
    const int = (v: string, lo: number, hi: number) => /^\d+$/.test(v) && Number(v) >= lo && Number(v) <= hi;
    if (!int(f.bedrooms, 0, 20)) errs.bedrooms = "0 to 20.";
    if (!int(f.bathrooms, 0, 20)) errs.bathrooms = "0 to 20.";
    if (!int(f.floor, 0, 200)) errs.floor = "0 to 200.";
    else if (building && Number(f.floor) > building.floors) errs.floor = `${building.code} has ${building.floors} floors.`;
    if (!isPositiveAmount(f.area_sqm)) errs.area_sqm = "A positive area, e.g. 112.5.";
    if (!isPositiveAmount(f.list_price)) errs.list_price = "A positive price in SAR.";
    if (Object.keys(errs).length) return s.reset(errs);
    s.reset();
    const values = {
      unit_type: f.unit_type, bedrooms: Number(f.bedrooms), bathrooms: Number(f.bathrooms), floor: Number(f.floor),
      area_sqm: f.area_sqm, view: f.view.trim() || null, list_price: f.list_price, is_public: publicListing, notes: f.notes.trim() || null,
    };
    if (unit) {
      const body = changedFields({ ...unit, view: unit.view, notes: unit.notes }, values);
      for (const k of LOCKED_WHEN_COMMITTED) if (committed) delete (body as Record<string, unknown>)[k];
      if (!Object.keys(body).length) { onClose(); return; }
      save.mutate(body, { onSuccess: () => { toast.success(`${unit.building.code}-${unit.unit_number} updated`); onClose(); }, onError: s.apply });
    } else {
      save.mutate({ ...values, building_id: f.building_id, unit_number: f.unit_number.trim().toUpperCase(), status: blocked ? "blocked" : "available" }, {
        onSuccess: (u) => { toast.success(`${u.building.code}-${u.unit_number} added`); onClose(); navigate(`/realestate/units/${u.id}`); },
        onError: s.apply,
      });
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className={`${scroll} max-w-xl`}>
        <DialogHeader title={unit ? `Edit ${unit.building.code}-${unit.unit_number}` : "Add unit"}
          description={unit ? "Status changes use Block / Make available; reserved and sold come only from reservations." : "New units start available (or blocked)."} />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={s.alert} />
          {committed && (
            <p className="flex items-start gap-2 rounded-[var(--radius-control)] border border-warning/40 bg-warning-subtle px-3 py-2 text-small text-fg-secondary">
              <Lock className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
              This unit is {unit?.status}. Type, size, floor and price are locked; only the view, bathrooms, listing and notes can change.
            </p>
          )}
          {!unit && (
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Project" htmlFor="u-project" required>
                <Select value={project} onValueChange={(v) => { setProject(v); set("building_id")(""); }} placeholder="Choose a project"
                  options={(projects.data?.items ?? []).map((p) => ({ value: p.id, label: p.name }))} />
              </FormField>
              <FormField label="Building" htmlFor="u-building" required error={s.errors.building_id}>
                <Select value={f.building_id || undefined} onValueChange={set("building_id")} disabled={!detail.data?.buildings.length}
                  placeholder={project ? (detail.isFetching ? "Loading…" : detail.data?.buildings.length ? "Choose a building" : "Add a building first") : "Choose a project first"}
                  options={(detail.data?.buildings ?? []).map((b) => ({ value: b.id, label: `${b.code} · ${b.name} (${b.floors} floors)` }))} />
              </FormField>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-3">
            {!unit && (
              <FormField label="Unit number" htmlFor="u-number" required error={s.errors.unit_number}>
                <Input maxLength={20} value={f.unit_number} onChange={(e) => set("unit_number")(e.target.value)} />
              </FormField>
            )}
            <FormField label="Type" htmlFor="u-type" required><Select value={f.unit_type} onValueChange={set("unit_type")} options={UNIT_TYPES} disabled={locked("unit_type")} /></FormField>
            <FormField label="Floor" htmlFor="u-floor" required error={s.errors.floor}><Input type="number" min={0} value={f.floor} disabled={locked("floor")} onChange={(e) => set("floor")(e.target.value)} /></FormField>
            <FormField label="Bedrooms" htmlFor="u-beds" required error={s.errors.bedrooms}><Input type="number" min={0} max={20} value={f.bedrooms} disabled={locked("bedrooms")} onChange={(e) => set("bedrooms")(e.target.value)} /></FormField>
            <FormField label="Bathrooms" htmlFor="u-baths" required error={s.errors.bathrooms}><Input type="number" min={0} max={20} value={f.bathrooms} onChange={(e) => set("bathrooms")(e.target.value)} /></FormField>
            <FormField label="Area (m²)" htmlFor="u-area" required error={s.errors.area_sqm}><Input inputMode="decimal" value={f.area_sqm} disabled={locked("area_sqm")} onChange={(e) => set("area_sqm")(e.target.value)} /></FormField>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="List price (SAR)" htmlFor="u-price" required error={s.errors.list_price}><Input inputMode="decimal" value={f.list_price} disabled={locked("list_price")} onChange={(e) => set("list_price")(e.target.value)} /></FormField>
            <FormField label="View" htmlFor="u-view" error={s.errors.view}><Input maxLength={60} value={f.view} onChange={(e) => set("view")(e.target.value)} /></FormField>
          </div>
          <FormField label="Notes" htmlFor="u-notes"><Textarea rows={2} maxLength={2000} value={f.notes} onChange={(e) => set("notes")(e.target.value)} /></FormField>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <div className="flex items-center gap-2"><Checkbox id="u-public" checked={publicListing} onCheckedChange={(v) => setPublic(v === true)} /><Label htmlFor="u-public">Public listing</Label></div>
            {!unit && <div className="flex items-center gap-2"><Checkbox id="u-blocked" checked={blocked} onCheckedChange={(v) => setBlocked(v === true)} /><Label htmlFor="u-blocked">Start blocked</Label></div>}
          </div>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={save.isPending}><Save /> {unit ? "Save changes" : "Add unit"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
