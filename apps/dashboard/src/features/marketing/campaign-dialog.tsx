import { Save } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FormAlert, FormField } from "@/components/system/forms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { Checkbox, Label } from "@/components/ui/primitives";
import { useProjects } from "@/features/realestate/api";
import { ApiError } from "@/lib/api-client";
import { useCampaignMutations, type Campaign, type Channel } from "./api";
import { CHANNEL_KEYS, CHANNELS } from "./logic";

const STATUSES = [{ value: "draft", label: "Draft" }, { value: "active", label: "Active" }, { value: "completed", label: "Completed" }];

export function CampaignDialog({ campaign, onClose }: { campaign?: Campaign; onClose: () => void }) {
  const { save } = useCampaignMutations(campaign?.id);
  const projects = useProjects({ page_size: 100 });
  const navigate = useNavigate();
  const [f, setF] = React.useState({
    name: campaign?.name ?? "", objective: campaign?.objective ?? "", description: campaign?.description ?? "",
    project_id: campaign?.project.id ?? "", start_date: campaign?.start_date ?? "", end_date: campaign?.end_date ?? "",
    status: (campaign?.status === "archived" ? "completed" : campaign?.status) ?? "draft",
  });
  const [channels, setChannels] = React.useState<Channel[]>(campaign?.channels ?? []);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [alert, setAlert] = React.useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => { setF((x) => ({ ...x, [k]: v })); setErrors((e) => ({ ...e, [k]: "" })); };
  const toggle = (c: Channel, on: boolean) => { setChannels((cs) => on ? [...cs, c] : cs.filter((x) => x !== c)); setErrors((e) => ({ ...e, channels: "" })); };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (f.name.trim().length < 3) errs.name = "Give the campaign a name (3+ characters).";
    if (f.objective.trim().length < 3) errs.objective = "State the objective.";
    if (!campaign && !f.project_id) errs.project_id = "Choose the project this campaign promotes.";
    if (!channels.length) errs.channels = "Choose at least one channel.";
    if (f.start_date && f.end_date && f.end_date < f.start_date) errs.end_date = "The end date can't be before the start date.";
    setErrors(errs);
    if (Object.keys(errs).length) return setAlert("Fix the highlighted fields.");
    setAlert(null);
    save.mutate({
      name: f.name.trim(), objective: f.objective.trim(), description: f.description.trim() || null, channels: CHANNEL_KEYS.filter((c) => channels.includes(c)),
      start_date: f.start_date || null, end_date: f.end_date || null, status: f.status as "draft" | "active" | "completed",
      ...(campaign ? {} : { project_id: f.project_id }),
    }, {
      onSuccess: (c) => { toast.success(campaign ? `${c.code} saved` : `${c.code} created`); onClose(); if (!campaign) navigate(`/marketing/campaigns/${c.id}`); },
      onError: (err) => {
        if (err instanceof ApiError) { setErrors(err.fieldErrors); setAlert(err.message); } else setAlert("Something went wrong. Try again.");
      },
    });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] max-w-xl overflow-y-auto">
        <DialogHeader title={campaign ? `Edit ${campaign.code}` : "New campaign"} description="A campaign promotes one project on the channels you choose." />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={alert} />
          <FormField label="Name" htmlFor="c-name" required error={errors.name}>
            <Input maxLength={150} value={f.name} onChange={(e) => set("name")(e.target.value)} />
          </FormField>
          <FormField label="Objective" htmlFor="c-objective" required error={errors.objective} hint="What should this campaign achieve?">
            <Input maxLength={300} value={f.objective} onChange={(e) => set("objective")(e.target.value)} />
          </FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Project" htmlFor="c-project" required error={errors.project_id} hint={campaign ? "A campaign's project can't change" : undefined}>
              <Select id="c-project" value={f.project_id || undefined} onValueChange={set("project_id")} disabled={Boolean(campaign)} placeholder="Choose a project…"
                options={(projects.data?.items ?? []).map((p) => ({ value: p.id, label: `${p.name} (${p.code})` }))} />
            </FormField>
            <FormField label="Status" htmlFor="c-status" required>
              <Select id="c-status" value={f.status} onValueChange={set("status")} options={STATUSES} />
            </FormField>
            <FormField label="Start date" htmlFor="c-start"><Input type="date" value={f.start_date} onChange={(e) => set("start_date")(e.target.value)} /></FormField>
            <FormField label="End date" htmlFor="c-end" error={errors.end_date}><Input type="date" value={f.end_date} onChange={(e) => set("end_date")(e.target.value)} /></FormField>
          </div>
          <fieldset>
            <legend className="mb-2 text-small font-medium">Channels <span className="text-danger">*</span></legend>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {CHANNEL_KEYS.map((c) => (
                <div key={c} className="flex items-center gap-2">
                  <Checkbox id={`ch-${c}`} checked={channels.includes(c)} onCheckedChange={(v) => toggle(c, v === true)} />
                  <Label htmlFor={`ch-${c}`}>{CHANNELS[c].label}</Label>
                </div>
              ))}
            </div>
            {errors.channels && <p className="mt-1 text-caption text-danger">{errors.channels}</p>}
          </fieldset>
          <FormField label="Description" htmlFor="c-desc" hint="Audience, key messages, notes for the team">
            <Textarea rows={3} maxLength={4000} value={f.description} onChange={(e) => set("description")(e.target.value)} />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={save.isPending}><Save /> {campaign ? "Save changes" : "Create campaign"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
