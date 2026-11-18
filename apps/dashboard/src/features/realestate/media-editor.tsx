import { ImageIcon, Plus, Star, Trash2, Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { Checkbox } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api-client";
import { IMAGE_UPLOAD, projectImageUrl, uploadProjectImage } from "./api";
import { coverIndex, imageFileProblem, isCoverCandidate, MEDIA_KINDS, type MediaRow, uploadedRow } from "./logic";

let next = 0;

/**
 * Project media rows: web links (each with its kind: only "Image" links can be the cover) and images uploaded from the
 * device. An uploaded image appears on the website and in brochures only once approved with its source and licence.
 * The first eligible image is the website's cover; "Set as cover" moves a row to the top.
 */
export function MediaEditor({ rows, onChange, error, projectId }: {
  rows: MediaRow[]; onChange: (rows: MediaRow[]) => void; error?: string;
  /** Needed to upload; a new project has to be saved first. */
  projectId?: string;
}) {
  const input = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);
  const update = (key: string, patch: Partial<MediaRow>) => onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const updateLocal = (r: MediaRow, patch: Partial<NonNullable<MediaRow["local"]>>) => update(r.key, { local: { ...r.local!, ...patch } });
  const remove = (key: string) => onChange(rows.filter((r) => r.key !== key));
  const makeCover = (key: string) => onChange([...rows.filter((r) => r.key === key), ...rows.filter((r) => r.key !== key)]);
  const cover = coverIndex(rows);

  const pick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !projectId) return;
    const problem = imageFileProblem(file);
    if (problem) return void toast.error(problem);
    setUploading(true);
    try {
      const up = await uploadProjectImage(projectId, file);
      onChange([...rows, uploadedRow(`up${next++}`, up.file)]);
      toast.success("Image uploaded — add its source and licence, approve it, then save");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "The image couldn't be uploaded");
    } finally {
      setUploading(false);
    }
  };

  const coverControl = (r: MediaRow, i: number) => (i === cover
    ? <span className="inline-flex items-center gap-1 rounded-full bg-brand-subtle px-2 py-0.5 text-caption font-medium text-brand"><Star className="size-3" aria-hidden />Website cover</span>
    : isCoverCandidate(r) && (
      <Button type="button" variant="ghost" size="sm" onClick={() => makeCover(r.key)} aria-label={`Set media ${i + 1} as cover`}>
        <Star /> Set as cover
      </Button>
    ));

  return (
    <fieldset className="space-y-2">
      <legend className="text-small font-medium">Media</legend>
      <p className="text-caption text-fg-muted">
        The first approved image is the website's cover. Uploaded images need a source and licence, and must be approved before
        they appear on the website or in brochures.
      </p>
      {rows.length === 0 && <p className="text-small text-fg-muted">No media yet.</p>}
      <ul className="space-y-2">
        {rows.map((r, i) => r.local ? (
          <li key={r.key} className="grid gap-3 rounded-[var(--radius-control)] border border-border p-2 sm:grid-cols-[7rem_1fr_auto]" data-testid="uploaded-image">
            {projectId && r.local.file
              ? <img src={projectImageUrl(projectId, r.local.file)} alt={r.local.caption || "Uploaded image"} className="aspect-[4/3] w-full rounded-[6px] bg-surface-subtle object-cover" />
              : <div className="grid aspect-[4/3] place-items-center rounded-[6px] bg-surface-subtle"><ImageIcon className="size-5 text-fg-muted" /></div>}
            <div className="min-w-0 space-y-2">
              <div className="flex flex-wrap items-center gap-2 text-small">
                <span className="font-medium">Uploaded image</span>{coverControl(r, i)}
              </div>
              <Input aria-label={`Media ${i + 1} caption`} placeholder="Caption (optional)" maxLength={150} value={r.local.caption ?? ""}
                onChange={(e) => updateLocal(r, { caption: e.target.value })} />
              <div className="grid gap-2 sm:grid-cols-2">
                <Input aria-label={`Media ${i + 1} source`} placeholder="Source (who made it)" maxLength={150} value={r.local.source ?? ""}
                  onChange={(e) => updateLocal(r, { source: e.target.value })} />
                <Input aria-label={`Media ${i + 1} licence`} placeholder="Licence / usage rights" maxLength={150} value={r.local.licence ?? ""}
                  onChange={(e) => updateLocal(r, { licence: e.target.value })} />
              </div>
              <label className="flex items-start gap-2 text-small">
                <Checkbox className="mt-0.5" checked={r.local.approved === true} aria-label={`Approve media ${i + 1}`}
                  onCheckedChange={(c) => updateLocal(r, { approved: c === true })} />
                <span>Approved for marketing use <span className="block text-caption text-fg-muted">Shown on the website and offered for brochures and posters</span></span>
              </label>
            </div>
            <Button type="button" variant="ghost" size="sm" aria-label={`Remove media ${i + 1}`} onClick={() => remove(r.key)}><Trash2 /></Button>
          </li>
        ) : (
          <li key={r.key} className="grid gap-2 rounded-[var(--radius-control)] border border-border p-2 sm:grid-cols-[8.5rem_1fr_auto]">
            <Select aria-label={`Media ${i + 1} kind`} value={r.kind} onValueChange={(v) => update(r.key, { kind: v })} options={MEDIA_KINDS} />
            <Input aria-label={`Media ${i + 1} link`} placeholder="https://…" value={r.url} inputMode="url" onChange={(e) => update(r.key, { url: e.target.value })} />
            <Button type="button" variant="ghost" size="sm" aria-label={`Remove media ${i + 1}`} onClick={() => remove(r.key)} className="sm:row-span-2"><Trash2 /></Button>
            <Input aria-label={`Media ${i + 1} caption`} placeholder="Caption (optional)" maxLength={150} value={r.caption}
              onChange={(e) => update(r.key, { caption: e.target.value })} className="sm:col-span-2" />
            {(i === cover || isCoverCandidate(r)) && <div className="sm:col-span-2">{coverControl(r, i)}</div>}
          </li>
        ))}
      </ul>
      {error && <p className="text-small text-danger" role="alert">{error}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="secondary" size="sm" disabled={!projectId} loading={uploading} onClick={() => input.current?.click()}>
          <Upload /> Upload image
        </Button>
        <Button type="button" variant="secondary" size="sm" onClick={() => onChange([...rows, { key: `new${next++}`, url: "", caption: "", kind: "image" }])}>
          <Plus /> Add media link
        </Button>
        {!projectId && <span className="text-caption text-fg-muted">Save the project first to upload images.</span>}
        <input ref={input} type="file" accept={IMAGE_UPLOAD.accept} className="hidden" onChange={(e) => void pick(e)} data-testid="image-file" />
      </div>
    </fieldset>
  );
}
