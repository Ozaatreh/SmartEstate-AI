import { AlertTriangle, Archive, CheckCircle2, ChevronDown, History, Save, Send, Sparkles, XCircle } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/system/badges";
import { MoneyText } from "@/components/system/data-display";
import { ConfirmDialog, FormAlert, FormField } from "@/components/system/forms";
import { PageHeader, Panel } from "@/components/system/layout-blocks";
import { ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/menu";
import { DecisionDialog } from "@/features/approvals/decision-dialog";
import { useApproval } from "@/features/approvals/api";
import { ApiError } from "@/lib/api-client";
import { formatDate, formatDateTime, formatRelative } from "@/lib/format";
import { humanize } from "@/lib/status";
import { cn } from "@/lib/utils";
import {
  checkFacts, useCampaign, useContent, useContentMutations, useMarketingAIStatus, useProjectFacts,
  type Campaign, type Channel, type ContentDetail, type FactWarning, type Language,
} from "./api";
import { CHANNELS, contentProblems, isRtl, parseHashtags } from "./logic";
import { ContentPreview } from "./preview";
import { ChannelLabel, ContentStatusBadge } from "./shared";

/** /marketing/content/new?campaign=… (create) and /marketing/content/:id (edit, review, history). */
export default function ContentEditorPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const detail = useContent(id);
  const campaignId = id ? detail.data?.campaign?.id : params.get("campaign") ?? undefined;
  const campaign = useCampaign(campaignId);
  if ((id && detail.isPending) || (campaignId && campaign.isPending)) return <ListSkeleton rows={8} />;
  if (id && detail.isError) return <ErrorState error={detail.error} onRetry={() => void detail.refetch()} className="min-h-[50vh]" />;
  if (campaign.isError) return <ErrorState error={campaign.error} onRetry={() => void campaign.refetch()} className="min-h-[50vh]" />;
  if (!campaign.data) return <ErrorState error={new Error("Open a campaign first.")} title="Choose a campaign" className="min-h-[50vh]" />;
  return <Editor key={`${id ?? "new"}-${detail.data?.version ?? 0}-${detail.data?.status ?? ""}`} campaign={campaign.data} content={detail.data} />;
}

function Editor({ campaign, content: c }: { campaign: Campaign; content?: ContentDetail }) {
  const navigate = useNavigate();
  const { save, submit, archive } = useContentMutations(c?.id);
  const facts = useProjectFacts(campaign.project.id);
  const ai = useMarketingAIStatus();
  const editable = !c || c.allowed_actions.includes("edit");
  const can = (a: string) => Boolean(c?.allowed_actions.includes(a));

  const [channel, setChannel] = React.useState<Channel>(c?.channel ?? campaign.channels[0] ?? "instagram");
  const [language, setLanguage] = React.useState<Language>(c?.language ?? "en");
  const [headline, setHeadline] = React.useState(c?.headline ?? "");
  const [body, setBody] = React.useState(c?.body ?? "");
  const [cta, setCta] = React.useState(c?.call_to_action ?? "");
  const [tagsRaw, setTagsRaw] = React.useState((c?.hashtags ?? []).join(" "));
  const [note, setNote] = React.useState("");
  const [serverErrors, setServerErrors] = React.useState<Record<string, string>>({});
  const [alert, setAlert] = React.useState<string | null>(null);
  const [warnings, setWarnings] = React.useState<FactWarning[]>(c?.fact_warnings ?? []);
  const [dialog, setDialog] = React.useState<"approve" | "reject" | "archive" | null>(null);
  const approval = useApproval(dialog === "approve" || dialog === "reject" ? c?.approval_id : null);

  const hashtags = parseHashtags(tagsRaw);
  const problems = contentProblems(channel, headline, body, cta, hashtags);
  const errors = { ...serverErrors, ...(editable ? problems : {}) };
  const dirty = !c || channel !== c.channel || language !== c.language || headline !== (c.headline ?? "") || body !== c.body
    || cta !== (c.call_to_action ?? "") || hashtags.join(" ") !== c.hashtags.join(" ");
  const rtl = isRtl(language);

  // Live facts check (debounced): flags prices, percentages and bedroom counts that don't match the project.
  React.useEffect(() => {
    if (!editable) return;
    const t = window.setTimeout(() => {
      checkFacts({ project_id: campaign.project.id, headline: headline || null, body, call_to_action: cta || null }).then(setWarnings).catch(() => undefined);
    }, 500);
    return () => window.clearTimeout(t);
  }, [editable, campaign.project.id, headline, body, cta]);

  const onSave = () => {
    if (Object.keys(problems).length) return setAlert("Fix the highlighted fields.");
    setAlert(null);
    save.mutate({
      ...(c ? {} : { campaign_id: campaign.id }), channel, language, headline: headline.trim() || null, body: body.trim(),
      call_to_action: cta.trim() || null, hashtags: CHANNELS[channel].hashtags ? hashtags : [], ...(c ? { note: note.trim() || null } : {}),
    }, {
      onSuccess: (d) => {
        setServerErrors({}); setNote("");
        toast.success(c ? `Saved as version ${d.version}` : `${d.code} created`, { description: d.status === "draft" && c?.status === "rejected" ? "Back to draft — submit it again when ready." : undefined });
        if (!c) navigate(`/marketing/content/${d.id}`, { replace: true });
      },
      onError: (err) => {
        if (err instanceof ApiError) { setServerErrors(err.fieldErrors); setAlert(err.message); } else setAlert("Couldn't save. Try again.");
      },
    });
  };

  const onSubmit = () => c && submit.mutate(c.id, {
    onSuccess: () => toast.success(`${c.code} submitted for review`, { description: "A marketing manager will approve or request changes." }),
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Couldn't submit"),
  });

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Campaigns", to: "/marketing/campaigns" }, { label: campaign.code, to: `/marketing/campaigns/${campaign.id}` }, { label: c?.code ?? "New content" }]}
        title={c ? `${CHANNELS[c.channel].label} · ${c.language === "ar" ? "Arabic" : "English"}` : "New content"}
        description={`${campaign.name} · ${campaign.project.name}`}
        meta={c && <>
          <ContentStatusBadge status={c.status} />
          <span className="text-small text-fg-secondary">Version {c.version}</span>
          {c.created_by && <span className="text-small text-fg-secondary">by {c.created_by.full_name}</span>}
          <span className="text-small text-fg-muted">updated {formatRelative(c.updated_at)}</span>
        </>}
        actions={<>
          {can("archive") && <Button onClick={() => setDialog("archive")}><Archive /> Archive</Button>}
          {c?.can_decide && <>
            <Button variant="danger" onClick={() => setDialog("reject")}><XCircle /> Request changes</Button>
            <Button variant="primary" onClick={() => setDialog("approve")}><CheckCircle2 /> Approve</Button>
          </>}
        </>}
      />

      {c?.status === "rejected" && c.rejection_comment && (
        <div role="status" className="mb-4 flex gap-3 rounded-[var(--radius-panel)] border border-danger/40 bg-danger/5 px-4 py-3">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
          <div className="text-body"><p className="font-medium">Changes requested</p><p className="text-fg-secondary">“{c.rejection_comment}” — edit and submit again.</p></div>
        </div>
      )}
      {c?.status === "approved" && (
        <p role="status" className="mb-4 rounded-[var(--radius-panel)] border border-success/40 bg-success/5 px-4 py-3 text-body">
          Approved{c.decided_at ? ` ${formatRelative(c.decided_at)}` : ""}. Approved content is ready to use — SmartEstate never publishes it automatically.
        </p>
      )}
      {c?.status === "pending_approval" && !c.can_decide && (
        <p role="status" className="mb-4 rounded-[var(--radius-panel)] border border-warning/40 bg-warning/5 px-4 py-3 text-body">
          In review since {c.submitted_at ? formatRelative(c.submitted_at) : "recently"} — editing is locked until a marketing manager decides.
          {c.decide_blocked_reason && <span className="block text-small text-fg-secondary">{c.decide_blocked_reason}</span>}
        </p>
      )}

      <div className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)_340px]">
        {/* ---------------------------------------------------------------- brief & facts */}
        <aside className="space-y-4">
          <Panel title="Settings">
            <div className="space-y-3 p-4">
              <FormField label="Channel" htmlFor="m-channel">
                <Select id="m-channel" value={channel} disabled={!editable} onValueChange={(v) => setChannel(v as Channel)}
                  options={campaign.channels.map((ch) => ({ value: ch, label: CHANNELS[ch].label }))} />
              </FormField>
              <fieldset disabled={!editable}>
                <legend className="mb-1.5 text-small font-medium">Language</legend>
                <div className="inline-flex rounded-[var(--radius-control)] border border-border p-0.5" role="radiogroup" aria-label="Language">
                  {(["en", "ar"] as const).map((l) => (
                    <button key={l} type="button" role="radio" aria-checked={language === l} onClick={() => setLanguage(l)}
                      className={cn("h-8 rounded-[calc(var(--radius-control)-2px)] px-3 text-small transition-colors disabled:opacity-60",
                        language === l ? "bg-primary text-primary-foreground" : "text-fg-secondary hover:text-fg")}>
                      {l === "en" ? "English" : "العربية"}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>
          </Panel>
          <FactsPanel facts={facts.data} loading={facts.isPending} />
        </aside>

        {/* ---------------------------------------------------------------- editor */}
        <section className="min-w-0 space-y-4">
          <Panel title="Copy" description={editable ? "Use only facts from the project panel — prices, amenities and availability come from live data." : "Read-only in this state."}
            actions={<Button size="sm" variant="ghost" disabled title={ai.data?.reason} aria-label="Draft with AI (unavailable)"><Sparkles /> Draft with AI</Button>}>
            <form className="space-y-4 p-4" onSubmit={(e) => { e.preventDefault(); onSave(); }} noValidate>
              <FormAlert message={alert} />
              <p className="flex items-start gap-2 rounded-[var(--radius-control)] bg-surface-subtle px-3 py-2 text-caption text-fg-muted">
                <Sparkles className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                {ai.data?.enabled ? "AI drafting is available." : (ai.data?.reason ?? "AI drafting is turned off. Write and edit content manually.")}
              </p>
              <FormField label={CHANNELS[channel].headlineLabel} htmlFor="m-headline" required={CHANNELS[channel].headlineRequired} error={errors.headline}>
                <Input id="m-headline" maxLength={150} value={headline} disabled={!editable} onChange={(e) => setHeadline(e.target.value)} lang={language} dir={rtl ? "rtl" : "ltr"} />
              </FormField>
              <FormField label="Text" htmlFor="m-body" required error={errors.body}>
                <Textarea id="m-body" rows={8} maxLength={5000} value={body} disabled={!editable} onChange={(e) => setBody(e.target.value)} lang={language} dir={rtl ? "rtl" : "ltr"} />
              </FormField>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label="Call to action" htmlFor="m-cta" error={errors.call_to_action}>
                  <Input id="m-cta" maxLength={120} value={cta} disabled={!editable} onChange={(e) => setCta(e.target.value)} lang={language} dir={rtl ? "rtl" : "ltr"} placeholder={rtl ? "احجز زيارتك" : "Book a viewing"} />
                </FormField>
                <FormField label="Hashtags" htmlFor="m-tags" error={errors.hashtags} hint={CHANNELS[channel].hashtags ? "Separated by spaces" : `Not used on ${CHANNELS[channel].label}`}>
                  <Input id="m-tags" value={tagsRaw} disabled={!editable || !CHANNELS[channel].hashtags} onChange={(e) => setTagsRaw(e.target.value)} lang={language} dir={rtl ? "rtl" : "ltr"} placeholder="#Riyadh #NewHome" />
                </FormField>
              </div>
              {c && editable && (
                <FormField label="What changed? (optional)" htmlFor="m-note" hint="Saved with the version history">
                  <Input id="m-note" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
                </FormField>
              )}
              {warnings.length > 0 && (
                <div role="alert" className="space-y-1 rounded-[var(--radius-control)] border border-warning/50 bg-warning/5 px-3 py-2">
                  <p className="flex items-center gap-1.5 text-small font-medium"><AlertTriangle className="size-4 text-warning" aria-hidden /> Check these against the project facts</p>
                  <ul className="space-y-0.5 text-small text-fg-secondary">
                    {warnings.map((w) => <li key={w.text}><span className="font-medium text-fg" dir="auto">“{w.text}”</span> — {w.message}</li>)}
                  </ul>
                </div>
              )}
              {editable && (
                <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border-subtle pt-4">
                  {c && dirty && <span className="mr-auto text-caption text-fg-muted">Unsaved changes</span>}
                  <Button type="submit" loading={save.isPending} disabled={c ? !dirty : false}><Save /> {c ? "Save draft" : "Create draft"}</Button>
                  {can("submit") && <Button type="button" variant="primary" onClick={onSubmit} loading={submit.isPending} disabled={dirty}
                    title={dirty ? "Save your changes first" : undefined}><Send /> Submit for review</Button>}
                </div>
              )}
            </form>
          </Panel>
        </section>

        {/* ---------------------------------------------------------------- preview, review, history */}
        <aside className="space-y-4">
          <Panel title="Preview" description="Nothing is posted from SmartEstate">
            <div className="p-4">
              <ContentPreview channel={channel} language={language} headline={headline} body={body} cta={cta} hashtags={CHANNELS[channel].hashtags ? hashtags : []} projectName={campaign.project.name} />
            </div>
          </Panel>
          {c && <ReviewPanel content={c} />}
          {c && <VersionsPanel content={c} canRestore={editable} onRestore={(v) => {
            setChannel(campaign.channels.includes(v.channel) ? v.channel : channel); setLanguage(v.language); setHeadline(v.headline ?? ""); setBody(v.body);
            setCta(v.call_to_action ?? ""); setTagsRaw(v.hashtags.join(" ")); setNote(`Restored text of version ${v.version}`);
            toast.info(`Version ${v.version} copied into the editor — save to keep it.`);
          }} />}
        </aside>
      </div>

      {(dialog === "approve" || dialog === "reject") && approval.data && (
        <DecisionDialog approval={approval.data} decision={dialog} onClose={() => setDialog(null)} />
      )}
      {c && <ConfirmDialog open={dialog === "archive"} onOpenChange={(o) => !o && setDialog(null)} loading={archive.isPending}
        title={`Archive ${c.code}?`} confirmLabel="Archive" description="Archived content is kept with its history but can't be edited or submitted."
        onConfirm={() => archive.mutate(c.id, {
          onSuccess: () => { toast.success(`${c.code} archived`); setDialog(null); },
          onError: (e) => { toast.error(e instanceof ApiError ? e.message : "Couldn't archive"); setDialog(null); },
        })} />}
    </>
  );
}

function FactsPanel({ facts: f, loading }: { facts?: import("./api").ProjectFacts; loading: boolean }) {
  return (
    <Panel title="Project facts" description="Live data — the only source for claims">
      {loading || !f ? <ListSkeleton rows={4} /> : (
        <div className="space-y-3 p-4 text-small">
          <div>
            <Link to={`/realestate/projects/${f.project.id}`} className="font-medium hover:underline">{f.project.name}</Link>
            <p className="text-fg-muted">{[f.district, f.city].filter(Boolean).join(", ")} · {humanize(f.status)}{f.handover_date ? ` · handover ${formatDate(f.handover_date)}` : ""}</p>
            <div className="mt-1 flex flex-wrap gap-1">
              <Badge tone={f.is_published ? "success" : "neutral"}>{f.is_published ? "On the website" : "Not published"}</Badge>
              {f.is_demo_data && <Badge tone="neutral">Fictional demo data</Badge>}
            </div>
          </div>
          <div>
            <p className="font-medium">Availability · {f.available_units} units{f.price_from_sar ? <> · from <MoneyText value={f.price_from_sar} /></> : null}</p>
            <ul className="mt-1 space-y-0.5 text-fg-secondary">
              {f.bedroom_options.map((b) => (
                <li key={b.bedrooms}>{b.bedrooms === 0 ? "Studio" : `${b.bedrooms} BR`}: {b.available} available · <MoneyText value={b.price_from_sar} />{b.price_to_sar !== b.price_from_sar && <>–<MoneyText value={b.price_to_sar} /></>}</li>
              ))}
              {!f.bedroom_options.length && <li>No units available.</li>}
            </ul>
          </div>
          {f.payment_plans.length > 0 && (
            <div>
              <p className="font-medium">Payment plans</p>
              <ul className="mt-1 space-y-0.5 text-fg-secondary">
                {f.payment_plans.map((p) => <li key={p.name}>{p.name}: {p.down_payment_pct}% down · {p.installments} {p.installment_frequency}{Number(p.handover_pct) ? ` · ${p.handover_pct}% at handover` : ""}</li>)}
              </ul>
            </div>
          )}
          {f.amenities.length > 0 && (
            <div><p className="font-medium">Amenities</p><p className="mt-1 text-fg-secondary">{f.amenities.join(" · ")}</p></div>
          )}
        </div>
      )}
    </Panel>
  );
}

function ReviewPanel({ content: c }: { content: ContentDetail }) {
  return (
    <Panel title="Review" description="Human approval by a marketing manager">
      {c.approvals.length ? (
        <ol className="divide-y divide-border-subtle">
          {c.approvals.map((r) => (
            <li key={r.id} className="space-y-1 px-4 py-3 text-small">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">Version {r.version ?? "—"}</span>
                <ContentStatusBadge status={r.status === "pending" ? "pending_approval" : r.status === "approved" ? "approved" : "rejected"} />
              </div>
              <p className="text-fg-muted">Submitted by {r.requested_by?.full_name ?? "—"} · <span title={formatDateTime(r.created_at)}>{formatRelative(r.created_at)}</span></p>
              {r.steps.map((s, i) => s.decided_by ? (
                <p key={i} className="text-fg-secondary">{humanize(s.status)} by {s.decided_by.full_name}{s.decided_at ? `, ${formatRelative(s.decided_at)}` : ""}{s.comment ? ` — “${s.comment}”` : ""}</p>
              ) : <p key={i} className="text-fg-muted">Waiting for {s.label.toLowerCase()}</p>)}
            </li>
          ))}
        </ol>
      ) : <p className="p-4 text-small text-fg-muted">Not submitted yet. Submit the draft when it's ready; a marketing manager approves it or requests changes.</p>}
    </Panel>
  );
}

function VersionsPanel({ content: c, canRestore, onRestore }: { content: ContentDetail; canRestore: boolean; onRestore: (v: ContentDetail["versions"][number]) => void }) {
  const [open, setOpen] = React.useState<number | null>(null);
  return (
    <Panel title={<span className="inline-flex items-center gap-1.5"><History className="size-4" aria-hidden /> Version history</span>} description={`${c.versions.length} saved version${c.versions.length === 1 ? "" : "s"}`}>
      <ol className="divide-y divide-border-subtle">
        {c.versions.map((v) => (
          <li key={v.version} className="px-4 py-2.5 text-small">
            <button type="button" className="flex w-full items-center justify-between gap-2 text-left" aria-expanded={open === v.version} onClick={() => setOpen(open === v.version ? null : v.version)}>
              <span><span className="font-medium">v{v.version}</span> · {v.note}</span>
              <ChevronDown className={cn("size-4 shrink-0 text-fg-muted transition-transform", open === v.version && "rotate-180")} aria-hidden />
            </button>
            <p className="text-caption text-fg-muted">{v.edited_by?.full_name ?? "—"} · <span title={formatDateTime(v.created_at)}>{formatRelative(v.created_at)}</span> · <ChannelLabel channel={v.channel} className="text-caption" /></p>
            {open === v.version && (
              <div className="mt-2 space-y-1 rounded-[var(--radius-control)] bg-surface-subtle p-2.5" lang={v.language} dir={isRtl(v.language) ? "rtl" : "ltr"}>
                {v.headline && <p className="font-medium">{v.headline}</p>}
                <p className="whitespace-pre-line break-words">{v.body}</p>
                {v.call_to_action && <p className="font-medium">{v.call_to_action}</p>}
                {v.hashtags.length > 0 && <p className="text-brand">{v.hashtags.join(" ")}</p>}
                {canRestore && v.version !== c.version && <Button size="sm" variant="ghost" className="mt-1" onClick={() => onRestore(v)}>Use this text</Button>}
              </div>
            )}
          </li>
        ))}
      </ol>
    </Panel>
  );
}
