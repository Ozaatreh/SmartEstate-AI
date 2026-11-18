import { Archive, Box, CheckCircle2, Download, Pencil, Plus, RotateCcw, Trash2, Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Badge, StatusBadge } from "@/components/system/badges";
import { ConfirmDialog, FormAlert, FormField } from "@/components/system/forms";
import { Panel } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { ApiError } from "@/lib/api-client";
import { formatDate } from "@/lib/format";
import { useUnits } from "./api";
import {
  fileProblem, formatBytes, REPRESENTATION_LABEL, useModelLimits, useModelMutations, useModels,
  type ModelInput, type PropertyModel, type Representation,
} from "./models3d-api";

const errorText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export function ModelsPanel({ projectId, canManage, isDemo }: { projectId: string; canManage: boolean; isDemo: boolean }) {
  const models = useModels(projectId);
  const [editing, setEditing] = React.useState<PropertyModel | "new" | null>(null);
  const [deleting, setDeleting] = React.useState<PropertyModel | null>(null);
  const m = useModelMutations(projectId);

  const act = (model: PropertyModel, action: "approve" | "archive" | "restore") =>
    m.act.mutate({ id: model.id, action }, {
      onSuccess: () => toast.success({ approve: "Model approved", archive: "Model archived", restore: "Model restored to draft" }[action]),
      onError: (e) => toast.error(errorText(e, "Couldn't update the model")),
    });

  return (
    <Panel title="3D models"
      description="GLB or self-contained glTF files. A model appears on the website only once approved, with its source and licence recorded, and only for published projects and public units."
      actions={canManage && <Button size="sm" onClick={() => setEditing("new")}><Plus /> Add model</Button>}>
      {isDemo && (
        <p className="border-b border-border-subtle px-4 py-2.5 text-small text-fg-secondary">
          Fictional demo project: only attach a model that is clearly illustrative — never present invented geometry as a real building.
        </p>
      )}
      {models.isPending ? <ListSkeleton rows={2} /> : models.isError ? <ErrorState error={models.error} onRetry={() => void models.refetch()} />
        : !models.data.length ? (
          <EmptyState icon={<Box className="size-5" />} title="No 3D models yet"
            description={canManage ? "Add a model, upload its GLB/glTF file, record its source and licence, then approve it." : "Approved models for this project will appear here."} />
        ) : (
          <ul className="divide-y divide-border-subtle">
            {models.data.map((x) => {
              const can = (a: string) => x.allowed_actions.includes(a);
              return (
                <li key={x.id} className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{x.title}</span>
                      <StatusBadge status={x.status} />
                      {x.unit_code && <Badge tone="neutral" dot={false}>Unit {x.unit_code}</Badge>}
                      {x.publicly_visible ? <Badge tone="success">On the website</Badge> : <Badge tone="neutral">Not public</Badge>}
                    </div>
                    <p className="text-small text-fg-secondary">{REPRESENTATION_LABEL[x.representation]}</p>
                    <p className="text-caption text-fg-muted">
                      {x.format ? `${x.format.toUpperCase()} · ${formatBytes(x.size_bytes)} · ${x.mesh_count} mesh${x.mesh_count === 1 ? "" : "es"} · v${x.file_version}` : "No file uploaded yet"}
                      {x.uploaded_by && ` · uploaded by ${x.uploaded_by.full_name} ${formatDate(x.uploaded_at)}`}
                      {x.approved_by && ` · approved by ${x.approved_by.full_name} ${formatDate(x.approved_at)}`}
                    </p>
                    <p className="text-caption text-fg-muted">Source: {x.source ?? "—"} · Licence: {x.licence ?? "—"}</p>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    {can("download") && <Button size="sm" asChild><a href={`/api/v1/realestate/models/${x.id}/file`} download><Download /> File</a></Button>}
                    {can("upload") && <UploadButton model={x} projectId={projectId} />}
                    {can("edit") && <Button size="sm" onClick={() => setEditing(x)}><Pencil /> Edit</Button>}
                    {can("approve") && <Button size="sm" variant="primary" loading={m.act.isPending} onClick={() => act(x, "approve")}><CheckCircle2 /> Approve</Button>}
                    {can("archive") && <Button size="sm" onClick={() => act(x, "archive")}><Archive /> Archive</Button>}
                    {can("restore") && <Button size="sm" onClick={() => act(x, "restore")}><RotateCcw /> Restore</Button>}
                    {can("delete") && <Button size="sm" onClick={() => setDeleting(x)} aria-label={`Delete ${x.title}`}><Trash2 /></Button>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      {editing && <ModelDialog projectId={projectId} model={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)} tone="danger" title={`Delete ${deleting?.title ?? "model"}?`}
        description="The record and its file are removed. This can't be undone." confirmLabel="Delete model" loading={m.remove.isPending}
        onConfirm={() => deleting && m.remove.mutate(deleting.id, {
          onSuccess: () => { toast.success("Model deleted"); setDeleting(null); },
          onError: (e) => { toast.error(errorText(e, "Couldn't delete")); setDeleting(null); },
        })} />
    </Panel>
  );
}

function UploadButton({ model, projectId }: { model: PropertyModel; projectId: string }) {
  const input = React.useRef<HTMLInputElement>(null);
  const limits = useModelLimits();
  const { upload } = useModelMutations(projectId);
  return (
    <>
      <input ref={input} type="file" accept=".glb,.gltf,model/gltf-binary,model/gltf+json" className="sr-only" aria-label={`Upload file for ${model.title}`}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          const problem = fileProblem(file, limits.data);
          if (problem) return void toast.error(problem);
          upload.mutate({ id: model.id, file }, {
            onSuccess: (x) => toast.success(`${file.name} uploaded (v${x.file_version}) — approve it to publish`),
            onError: (err) => toast.error(errorText(err, "Upload failed")),
          });
        }} />
      <Button size="sm" loading={upload.isPending} onClick={() => input.current?.click()}><Upload /> {model.format ? "Replace file" : "Upload file"}</Button>
    </>
  );
}

function ModelDialog({ projectId, model, onClose }: { projectId: string; model?: PropertyModel; onClose: () => void }) {
  const { create, update } = useModelMutations(projectId);
  const units = useUnits({ project_id: projectId, page_size: 200, sort: "unit_number" });
  const [f, setF] = React.useState({
    title: model?.title ?? "", unit_id: model?.unit_id ?? "", representation: (model?.representation ?? "design") as Representation,
    caption: model?.caption ?? "", source: model?.source ?? "", licence: model?.licence ?? "",
  });
  const [alert, setAlert] = React.useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const save = model ? update : create;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (f.title.trim().length < 2) return setAlert("Enter a title.");
    const body: ModelInput = {
      title: f.title.trim(), unit_id: f.unit_id || null, representation: f.representation,
      caption: f.caption.trim() || null, source: f.source.trim() || null, licence: f.licence.trim() || null,
    };
    const opts = {
      onSuccess: () => { toast.success(model ? "Model updated" : "Model added — upload its file next"); onClose(); },
      onError: (err: unknown) => setAlert(errorText(err, "Couldn't save the model")),
    };
    if (model) update.mutate({ id: model.id, ...body }, opts); else create.mutate(body, opts);
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] max-w-lg overflow-y-auto">
        <DialogHeader title={model ? `Edit ${model.title}` : "Add 3D model"}
          description={model?.status === "approved" ? "Saving changes sends the model back to draft for approval." : "Describe the model honestly — the website shows what it represents."} />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={alert} />
          <FormField label="Title" htmlFor="m-title" required><Input id="m-title" maxLength={150} value={f.title} onChange={(e) => set("title")(e.target.value)} /></FormField>
          <FormField label="What it represents" htmlFor="m-rep" required>
            <Select id="m-rep" value={f.representation} onValueChange={set("representation")}
              options={(Object.keys(REPRESENTATION_LABEL) as Representation[]).map((r) => ({ value: r, label: REPRESENTATION_LABEL[r] }))} />
          </FormField>
          <FormField label="Unit (optional)" htmlFor="m-unit" hint="Leave empty for a project-level model">
            <Select id="m-unit" value={f.unit_id || "none"} onValueChange={(v) => set("unit_id")(v === "none" ? "" : v)}
              options={[{ value: "none", label: "Whole project" }, ...(units.data?.items ?? []).map((u) => ({ value: u.id, label: `${u.building.code}-${u.unit_number}` }))]} />
          </FormField>
          <FormField label="Caption (shown publicly)" htmlFor="m-caption"><Textarea id="m-caption" rows={2} maxLength={500} value={f.caption} onChange={(e) => set("caption")(e.target.value)} /></FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Source" htmlFor="m-source" hint="Who made it"><Input id="m-source" maxLength={200} value={f.source} onChange={(e) => set("source")(e.target.value)} /></FormField>
            <FormField label="Licence" htmlFor="m-licence" hint="Rights to show it"><Input id="m-licence" maxLength={200} value={f.licence} onChange={(e) => set("licence")(e.target.value)} /></FormField>
          </div>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={save.isPending}>{model ? "Save changes" : "Add model"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
