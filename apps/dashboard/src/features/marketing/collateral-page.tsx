import { AlertTriangle, Download, FileText, ImageIcon, Info, LayoutTemplate, ShieldCheck, Upload } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/system/badges";
import { MoneyText } from "@/components/system/data-display";
import { FormField } from "@/components/system/forms";
import { PageHeader, Panel } from "@/components/system/layout-blocks";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { Checkbox, Switch, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api-client";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { IMAGE_UPLOAD } from "@/features/realestate/api";
import { imageFileProblem } from "@/features/realestate/logic";
import type { Language } from "./api";
import {
  useBrochurePreview,
  useCollateralOptions,
  useCollateralProjects,
  useDownload,
  usePosterPreview,
  useUploadCollateralImage,
  type CollateralOptions,
  type Cta,
  type FactSheet,
  type ImageRights,
  type PosterFormat,
  type PosterTemplate,
  type Section,
} from "./collateral-api";

const ALL_SECTIONS: Section[] = ["overview", "location", "amenities", "units", "prices", "payment_plans", "contact"];
const MISSING_LABEL: Record<string, string> = {
  images: "No approved project images — a neutral placeholder is used",
  description: "No project description",
  amenities: "No amenities recorded",
  units: "No available public units — unit table and prices are left out",
  payment_plans: "No payment plans cleared for marketing",
  handover_date: "No handover date",
  contact: "Contact details aren't configured (COLLATERAL_CONTACT_*) — the contact section is left out",
};
// A section is offered only when the project has data for it.
const SECTION_NEEDS: Partial<Record<Section, string>> = {
  overview: "description", amenities: "amenities", units: "units", prices: "units", payment_plans: "payment_plans", contact: "contact",
};

export default function CollateralPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "poster" ? "poster" : "brochure";
  const projects = useCollateralProjects();
  const [chosen, setProjectId] = React.useState<string>();
  const projectId = chosen ?? projects.data?.[0]?.id;
  const [language, setLanguage] = React.useState<Language>("en");
  const options = useCollateralOptions(projectId);

  return (
    <>
      <PageHeader
        title="Brochures & posters"
        description="Print-ready brochures (PDF) and social posters (PNG) built from the project's live data. Every figure is read from the database when you generate, and the file is checked before download. Nothing is published."
      />
      {projects.isPending ? <ListSkeleton rows={4} /> : projects.isError ? <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />
        : !projects.data.length ? (
          <EmptyState icon={<FileText className="size-5" />} title="No published projects"
            description="Brochures and posters can only be made for projects published on the website. Publish a project in Real estate first." />
        ) : (
          <div className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
            <aside className="space-y-4">
              <Panel title="Project">
                <div className="space-y-4 p-4">
                  <FormField label="Project" htmlFor="c-project">
                    <Select id="c-project" value={projectId} onValueChange={setProjectId}
                      options={projects.data.map((p) => ({ value: p.id, label: `${p.name} (${p.code})` }))} />
                  </FormField>
                  <LanguageToggle value={language} onChange={setLanguage} />
                </div>
              </Panel>
              {options.isPending ? <ListSkeleton rows={4} /> : options.isError ? <ErrorState error={options.error} onRetry={() => void options.refetch()} />
                : <FactsPanel facts={options.data.facts} />}
            </aside>
            <section className="min-w-0">
              <Tabs value={tab} onValueChange={(v) => setParams(v === "poster" ? { tab: "poster" } : {}, { replace: true })}>
                <TabsList className="mb-4">
                  <TabsTrigger value="brochure">Brochure (PDF)</TabsTrigger>
                  <TabsTrigger value="poster">Social poster (PNG)</TabsTrigger>
                </TabsList>
                {options.data && projectId && (
                  <>
                    <TabsContent value="brochure"><BrochureTab key={projectId} options={options.data} projectId={projectId} language={language} /></TabsContent>
                    <TabsContent value="poster"><PosterTab key={projectId} options={options.data} projectId={projectId} language={language} /></TabsContent>
                  </>
                )}
              </Tabs>
            </section>
          </div>
        )}
    </>
  );
}

function LanguageToggle({ value, onChange }: { value: Language; onChange: (l: Language) => void }) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-small font-medium">Language</legend>
      <div className="inline-flex rounded-[var(--radius-control)] border border-border p-0.5" role="radiogroup" aria-label="Language">
        {(["en", "ar"] as const).map((l) => (
          <button key={l} type="button" role="radio" aria-checked={value === l} onClick={() => onChange(l)}
            className={cn("h-8 rounded-[calc(var(--radius-control)-2px)] px-3 text-small transition-colors",
              value === l ? "bg-primary text-primary-foreground" : "text-fg-secondary hover:text-fg")}>
            {l === "en" ? "English" : "العربية"}
          </button>
        ))}
      </div>
      {value === "ar" && <p className="mt-2 text-caption text-fg-muted">Headings and labels are in Arabic; project names, descriptions and amenities appear as stored (no machine translation).</p>}
    </fieldset>
  );
}

function FactsPanel({ facts: f }: { facts: FactSheet }) {
  return (
    <Panel title="Verified facts" description={`Read from the database ${formatDateTime(f.as_of)}`}>
      <dl className="divide-y divide-border-subtle text-small">
        <Row label="Starting price">{f.price_from_sar ? <MoneyText value={f.price_from_sar} /> : <span className="text-fg-muted">Not available</span>}</Row>
        <Row label="Homes available">{f.available_units}</Row>
        <Row label="Unit types">{f.unit_types.length ? f.unit_types.map((u) => (u.bedrooms === 0 ? "Studio" : `${u.bedrooms} BR`)).join(" · ") : "—"}</Row>
        <Row label="Handover">{f.handover_date ? formatDate(f.handover_date) : "—"}</Row>
        <Row label="Payment plans">
          {f.payment_plans.length ? f.payment_plans.map((p) => p.name).join(", ") : "—"}
        </Row>
        <Row label="Amenities">{f.amenities.length}</Row>
        <Row label="Approved images">{f.images.length}</Row>
      </dl>
      {f.excluded_plans > 0 && (
        <p className="flex gap-2 border-t border-border-subtle px-4 py-3 text-caption text-fg-secondary">
          <ShieldCheck className="mt-px size-3.5 shrink-0 text-success" />
          {f.excluded_plans} payment plan{f.excluded_plans > 1 ? "s are" : " is"} left out because {f.excluded_plans > 1 ? "they aren't" : "it isn't"} cleared for marketing.
        </p>
      )}
      {f.is_demo_data && (
        <p className="flex gap-2 border-t border-border-subtle px-4 py-3 text-caption text-fg-secondary">
          <Info className="mt-px size-3.5 shrink-0" /> Fictional demo project — every file carries a demo disclosure.
        </p>
      )}
      {f.missing.length > 0 && (
        <div className="border-t border-border-subtle px-4 py-3">
          <p className="mb-1.5 flex items-center gap-1.5 text-caption font-medium text-warning"><AlertTriangle className="size-3.5" /> Missing — left out, never invented</p>
          <ul className="space-y-1 text-caption text-fg-secondary">{f.missing.map((m) => <li key={m}>· {MISSING_LABEL[m] ?? m}</li>)}</ul>
        </div>
      )}
    </Panel>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="flex justify-between gap-4 px-4 py-2"><dt className="text-fg-muted">{label}</dt><dd className="text-right font-medium">{children}</dd></div>;
}

function ImagePicker({ facts, value, onChange }: { facts: FactSheet; value: string | null; onChange: (id: string | null) => void }) {
  const [uploading, setUploading] = React.useState(false);
  const label = (i: FactSheet["images"][number]) => `${i.caption ?? i.source} · ${i.origin === "upload" ? "brochure only" : "project image"}`;
  return (
    <div className="space-y-3">
      {facts.images.length ? (
        <Select value={value ?? "none"} onValueChange={(v) => onChange(v === "none" ? null : v)} aria-label="Image"
          options={[{ value: "none", label: "Neutral placeholder" }, ...facts.images.map((i) => ({ value: i.id, label: label(i) }))]} />
      ) : (
        <div className="flex gap-3 rounded-[var(--radius-control)] border border-dashed border-border-strong p-3 text-caption text-fg-secondary">
          <ImageIcon className="size-4 shrink-0 text-fg-muted" />
          <span>No approved images for this project yet, so layouts use a neutral placeholder. Approve a project image, or upload one here.</span>
        </div>
      )}
      {uploading
        ? <CollateralImageUpload projectId={facts.project_id} onDone={(id) => { setUploading(false); if (id) onChange(id); }} />
        : <Button type="button" variant="secondary" size="sm" className="w-full" onClick={() => setUploading(true)}><Upload /> Upload a different image</Button>}
    </div>
  );
}

/** Upload form for a brochure/poster-only image: the file plus its source and licence (printed as the credit). */
function CollateralImageUpload({ projectId, onDone }: { projectId: string; onDone: (id: string | null) => void }) {
  const upload = useUploadCollateralImage(projectId);
  const [file, setFile] = React.useState<File | null>(null);
  const [rights, setRights] = React.useState<ImageRights>({ source: "", licence: "", caption: "" });
  const [error, setError] = React.useState<string | null>(null);
  const submit = () => {
    if (!file) return setError("Choose an image.");
    const problem = imageFileProblem(file);
    if (problem) return setError(problem);
    if (!rights.source.trim() || !rights.licence.trim()) return setError("Record the image's source and licence.");
    setError(null);
    upload.mutate({ file, rights }, {
      onSuccess: (img) => { toast.success("Image uploaded for brochures and posters"); onDone(img.id); },
      onError: (e) => setError(e instanceof ApiError ? e.message : "The image couldn't be uploaded"),
    });
  };
  const field = (k: keyof ImageRights, label: string, placeholder: string) => (
    <label className="block space-y-1 text-caption font-medium">{label}
      <Input value={rights[k]} maxLength={150} placeholder={placeholder} onChange={(e) => setRights((r) => ({ ...r, [k]: e.target.value }))} />
    </label>
  );
  return (
    <div className="space-y-2.5 rounded-[var(--radius-control)] border border-border p-3" data-testid="collateral-upload">
      <label className="block space-y-1 text-caption font-medium">Image file
        <input type="file" accept={IMAGE_UPLOAD.accept} aria-label="Image file" className="block w-full text-caption file:mr-2 file:rounded-[6px] file:border file:border-border file:bg-surface file:px-2 file:py-1"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      {field("source", "Source", "Who made it")}
      {field("licence", "Licence", "Usage rights")}
      {field("caption", "Caption (optional)", "")}
      <p className="text-caption text-fg-muted">Used only for this project's brochures and posters — not added to the project or the website.</p>
      {error && <p className="text-caption text-danger" role="alert">{error}</p>}
      <div className="flex gap-2">
        <Button type="button" size="sm" variant="primary" loading={upload.isPending} onClick={submit}><Upload /> Upload</Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => onDone(null)}>Cancel</Button>
      </div>
    </div>
  );
}

function downloadError(e: unknown) {
  toast.error(e instanceof ApiError ? e.message : "Couldn't generate the file");
}

// ------------------------------------------------------------------ brochure
function BrochureTab({ options, projectId, language }: { options: CollateralOptions; projectId: string; language: Language }) {
  const facts = options.facts;
  const available = (s: Section) => !SECTION_NEEDS[s] || !facts.missing.includes(SECTION_NEEDS[s]!);
  const [sections, setSections] = React.useState<Section[]>(() => ALL_SECTIONS.filter(available));
  const [imageId, setImageId] = React.useState<string | null>(facts.images[0]?.id ?? null);
  const req = { project_id: projectId, language, sections, image_id: imageId };
  const preview = useBrochurePreview(req);
  const download = useDownload("brochure");

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <div className="space-y-4">
        <Panel title="Include">
          <div className="space-y-2.5 p-4">
            <p className="text-caption text-fg-muted">Cover, demo disclosure and data date are always included.</p>
            {options.sections.map((s) => {
              const id = s.id as Section;
              const ok = available(id);
              return (
                <label key={id} className={cn("flex items-start gap-2.5 text-small", !ok && "opacity-50")}>
                  <Checkbox className="mt-0.5" checked={sections.includes(id)} disabled={!ok}
                    onCheckedChange={(c) => setSections((cur) => (c ? ALL_SECTIONS.filter((x) => x === id || cur.includes(x)) : cur.filter((x) => x !== id)))} />
                  <span>{s.label}{!ok && <span className="block text-caption text-fg-muted">No data for this section</span>}</span>
                </label>
              );
            })}
          </div>
        </Panel>
        <Panel title="Cover image"><div className="p-4"><ImagePicker facts={facts} value={imageId} onChange={setImageId} /></div></Panel>
        <Button variant="primary" className="w-full" loading={download.isPending} disabled={preview.isError}
          onClick={() => download.mutate(req, { onSuccess: (f) => toast.success(`Downloaded ${f.filename}`), onError: downloadError })}>
          <Download /> Download PDF
        </Button>
        <p className="text-caption text-fg-muted">A4 portrait, print-ready PDF. Checked against the database before download.</p>
      </div>
      <PreviewFrame title="Brochure preview" html={preview.data?.html} width={794} height={preview.data ? pageCount(preview.data.html) * 1123 : 1123}
        loading={preview.isPending} fetching={preview.isFetching} error={preview.error} />
    </div>
  );
}

const pageCount = (html: string) => Math.max(1, (html.match(/<section class="page/g) ?? []).length);

// ------------------------------------------------------------------ poster
function PosterTab({ options, projectId, language }: { options: CollateralOptions; projectId: string; language: Language }) {
  const facts = options.facts;
  const [format, setFormat] = React.useState<PosterFormat>("instagram_post");
  const [template, setTemplate] = React.useState<PosterTemplate>("classic");
  const [imageId, setImageId] = React.useState<string | null>(facts.images[0]?.id ?? null);
  const [showPrice, setShowPrice] = React.useState(true);
  const [picked, setPicked] = React.useState<string[]>(() => options.key_facts.en.filter((o) => ["bedrooms", "handover", "available"].includes(o.id)).map((o) => o.id).slice(0, 3));
  const [cta, setCta] = React.useState<Cta>("book_viewing");
  const req = { project_id: projectId, language, format, template, image_id: imageId, show_price: showPrice, facts: picked, cta };
  const preview = usePosterPreview(req);
  const download = useDownload("poster");
  const size = options.formats.find((f) => f.id === format)!;
  const keyFacts = options.key_facts[language];

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <div className="space-y-4">
        <Panel title="Format">
          <div className="grid gap-2 p-4" role="radiogroup" aria-label="Format">
            {options.formats.map((f) => (
              <button key={f.id} type="button" role="radio" aria-checked={format === f.id} aria-label={`${f.label}, ${f.width} by ${f.height} pixels`} onClick={() => setFormat(f.id)}
                className={cn("flex items-center justify-between rounded-[var(--radius-control)] border px-3 py-2 text-left text-small transition-colors",
                  format === f.id ? "border-brand bg-brand-subtle" : "border-border hover:border-border-strong")}>
                <span className="font-medium">{f.label}</span>
                <span className="tabular text-caption text-fg-muted">{f.width} × {f.height}</span>
              </button>
            ))}
          </div>
        </Panel>
        <Panel title="Layout">
          <div className="space-y-4 p-4">
            <FormField label="Template" htmlFor="p-template">
              <Select id="p-template" value={template} onValueChange={(v) => setTemplate(v as PosterTemplate)}
                options={options.templates.map((t) => ({ value: t.id, label: t.label }))} />
            </FormField>
            <div><p className="mb-1.5 text-small font-medium">Image</p><ImagePicker facts={facts} value={imageId} onChange={setImageId} /></div>
            <label className="flex items-center justify-between gap-3 text-small">
              <span>Show starting price{facts.price_from_sar ? "" : " (not available)"}</span>
              <Switch label="Show starting price" checked={showPrice && !!facts.price_from_sar} disabled={!facts.price_from_sar} onCheckedChange={setShowPrice} />
            </label>
            <FormField label="Call to action" htmlFor="p-cta">
              <Select id="p-cta" value={cta} onValueChange={(v) => setCta(v as Cta)}
                options={options.ctas[language].map((c) => ({ value: c.id, label: c.label }))} />
            </FormField>
          </div>
        </Panel>
        <Panel title="Key facts" description={`Up to 3 · ${picked.length} chosen`}>
          <div className="max-h-72 space-y-2 overflow-y-auto p-4" dir={language === "ar" ? "rtl" : "ltr"}>
            {keyFacts.map((o) => {
              const on = picked.includes(o.id);
              return (
                <label key={o.id} className={cn("flex items-start gap-2.5 text-small", !on && picked.length >= 3 && "opacity-50")}>
                  <Checkbox className="mt-0.5" checked={on} disabled={!on && picked.length >= 3}
                    onCheckedChange={(c) => setPicked((cur) => (c ? [...cur, o.id] : cur.filter((x) => x !== o.id)))} />
                  <span lang={language}>{o.label}</span>
                </label>
              );
            })}
          </div>
        </Panel>
        <Button variant="primary" className="w-full" loading={download.isPending} disabled={preview.isError}
          onClick={() => download.mutate(req, { onSuccess: (f) => toast.success(`Downloaded ${f.filename}`), onError: downloadError })}>
          <Download /> Download PNG
        </Button>
        <p className="text-caption text-fg-muted">{size.label}, {size.width} × {size.height} px. Download only — nothing is posted.</p>
      </div>
      <PreviewFrame title="Poster preview" html={preview.data?.html} width={size.width} height={size.height} maxHeight={720}
        loading={preview.isPending} fetching={preview.isFetching} error={preview.error}
        caption={<><LayoutTemplate className="size-3.5" /> {size.label} · {size.width} × {size.height}</>} />
    </div>
  );
}

// ------------------------------------------------------------------ preview
function PreviewFrame({ title, html, width, height, maxHeight, loading, fetching, error, caption }: {
  title: string; html?: string; width: number; height: number; maxHeight?: number; loading: boolean; fetching: boolean;
  error: unknown; caption?: React.ReactNode;
}) {
  const box = React.useRef<HTMLDivElement>(null);
  const [boxWidth, setBoxWidth] = React.useState(0);
  React.useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setBoxWidth(e!.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const scale = boxWidth ? Math.min(boxWidth / width, maxHeight ? maxHeight / height : Infinity, 1) : 0;

  return (
    <Panel title={title} actions={<span className="flex items-center gap-2 text-caption text-fg-muted">{caption}{fetching && <Badge tone="neutral">Updating…</Badge>}</span>}>
      <div ref={box} className="bg-surface-sunken p-4">
        {error ? <ErrorState error={error} /> : loading || !html || !scale ? <div className="aspect-[3/4] w-full animate-pulse rounded bg-surface-subtle" /> : (
          <div className="mx-auto overflow-hidden rounded shadow-md" style={{ width: width * scale, height: height * scale }}>
            <iframe title={title} srcDoc={html} sandbox="" width={width} height={height}
              style={{ transform: `scale(${scale})`, transformOrigin: "top left", border: 0, display: "block", background: "#fff" }} />
          </div>
        )}
      </div>
    </Panel>
  );
}
