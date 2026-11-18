import { ArrowDown, Filter, Lightbulb, Play, RotateCcw, Save, ShieldCheck } from "lucide-react";
import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge, Chip } from "@/components/system/badges";
import { FormAlert, FormField } from "@/components/system/forms";
import { PageHeader, Panel } from "@/components/system/layout-blocks";
import { ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api-client";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useRunWorkflow, useUpdateWorkflow, useWorkflow, type WorkflowDetail } from "./api";
import { ExecutionsTable } from "./executions-page";
import { TriggerSummary } from "./shared";

export default function WorkflowDetailPage() {
  const { key } = useParams();
  const q = useWorkflow(key);
  if (q.isPending) return <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={5} /></div>;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} className="min-h-[50vh]" />;
  return <Detail wf={q.data} />;
}

function Detail({ wf }: { wf: WorkflowDetail }) {
  const update = useUpdateWorkflow(wf.key);
  const run = useRunWorkflow(wf.key);
  const navigate = useNavigate();
  const [tab, setTab] = React.useState("overview");

  const toggle = (enabled: boolean) => update.mutate({ is_enabled: enabled }, {
    onSuccess: () => toast.success(enabled ? `${wf.name} enabled` : `${wf.name} disabled`, { description: enabled ? undefined : "New events won't start this workflow." }),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't update the workflow"),
  });
  const runNow = () => run.mutate(undefined, {
    onSuccess: (r) => { toast.success("Run queued", { description: "A worker will pick it up within seconds." }); navigate(`/automation/executions/${r.execution_id}`); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't start the run"),
  });

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Automation", to: "/automation" }, { label: wf.category }]}
        title={wf.name}
        description={wf.description}
        meta={<><Chip>{wf.category}</Chip><Chip>v{wf.version}</Chip><code className="text-caption text-fg-muted">{wf.key}</code>
          {!wf.is_registered && <Badge tone="danger">Not registered in code</Badge>}</>}
        actions={<>
          <label className="mr-1 flex items-center gap-2 text-small font-medium">
            <Switch checked={wf.is_enabled} onCheckedChange={toggle} disabled={!wf.can_manage || update.isPending} label={`Enable ${wf.name}`} />
            {wf.is_enabled ? "Enabled" : "Disabled"}
          </label>
          {wf.schedule_minutes && wf.can_operate && <Button variant="primary" onClick={runNow} loading={run.isPending} disabled={!wf.is_enabled}><Play /> Run now</Button>}
        </>}
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="configuration">Configuration</TabsTrigger>
          <TabsTrigger value="executions">Executions</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
          <Panel title="Pipeline" description="Steps run in order; each commits in its own transaction and is not repeated on retry.">
            <ol className="p-4">
              <li className="mb-2 rounded-[var(--radius-control)] border border-dashed border-border-strong px-3 py-2 text-small">
                <p className="mb-1.5 font-medium">Trigger</p><TriggerSummary workflow={wf} />
              </li>
              {wf.conditions.length > 0 && <>
                <Arrow />
                <li className="rounded-[var(--radius-control)] border border-border bg-surface-subtle px-3 py-2 text-small">
                  <p className="flex items-center gap-1.5 font-medium"><Filter className="size-3.5 text-fg-muted" /> Only if</p>
                  <ul className="mt-1 list-disc pl-5 text-fg-secondary">{wf.conditions.map((c) => <li key={c}>{c}</li>)}</ul>
                </li>
              </>}
              {wf.steps.map((s, i) => (
                <React.Fragment key={s.key}>
                  <Arrow />
                  <li className="rounded-[var(--radius-control)] border border-border px-3 py-2.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="tabular grid size-5 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">{i + 1}</span>
                      <p className="font-medium">{s.label}</p>
                      {s.advisory && <Badge tone="ai" dot={false}><Lightbulb className="size-3" /> Advisory</Badge>}
                      {s.on_error === "continue" && <Badge tone="neutral" dot={false}>Optional</Badge>}
                    </div>
                    <p className="mt-1 text-small text-fg-secondary">{s.action_description || s.action_label}</p>
                    <p className="mt-1 flex flex-wrap gap-x-3 text-caption text-fg-muted"><code>{s.action}</code>{s.condition && <span>Runs when: {s.condition.toLowerCase()}</span>}</p>
                  </li>
                </React.Fragment>
              ))}
            </ol>
          </Panel>
          <div className="space-y-4">
            <Panel title="Status">
              <dl className="divide-y divide-border-subtle text-body">
                <Row label="Last 24 h" value={<span className="tabular">{wf.stats.succeeded} ok · {wf.stats.failed} failed · {wf.stats.skipped} skipped</span>} />
                <Row label="Running / queued" value={<span className="tabular">{wf.stats.running} / {wf.stats.pending}</span>} />
                {wf.schedule_minutes && <Row label="Next scheduled run" value={formatDateTime(wf.next_run_at)} />}
                {wf.schedule_minutes && <Row label="Last scheduled run" value={formatRelative(wf.last_run_at)} />}
                <Row label="Time limit" value={`${wf.timeout_seconds} s per attempt`} />
                <Row label="Attempts" value={`up to ${wf.max_attempts}, exponential backoff`} />
              </dl>
            </Panel>
            <p className="flex gap-2 rounded-[var(--radius-panel)] border border-border bg-surface-subtle p-3 text-small text-fg-secondary">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" />
              Workflow actions run through the same services as the app, so business rules, permissions and budget controls still apply. Advisory steps only recommend.
            </p>
          </div>
        </TabsContent>

        <TabsContent value="configuration"><ConfigForm wf={wf} /></TabsContent>
        <TabsContent value="executions"><ExecutionsTable fixedWorkflow={wf.key} /></TabsContent>
      </Tabs>
    </>
  );
}

function Arrow() {
  return <li aria-hidden className="flex justify-center py-1 text-fg-muted"><ArrowDown className="size-3.5" /></li>;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="flex items-center justify-between gap-4 px-4 py-2.5"><dt className="text-small text-fg-muted">{label}</dt><dd className="text-right">{value}</dd></div>;
}

function ConfigForm({ wf }: { wf: WorkflowDetail }) {
  const update = useUpdateWorkflow(wf.key);
  const initial = React.useMemo(() => ({
    params: Object.fromEntries(wf.parameters.map((p) => [p.name, typeof p.value === "boolean" ? p.value : String(p.value)])) as Record<string, string | boolean>,
    timeout: String(wf.timeout_seconds), attempts: String(wf.max_attempts),
  }), [wf]);
  const [values, setValues] = React.useState(initial);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const dirty = JSON.stringify(values) !== JSON.stringify(initial);
  const readOnly = !wf.can_manage;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    const params: Record<string, number | boolean> = {};
    for (const p of wf.parameters) {
      const raw = values.params[p.name];
      if (p.type === "bool") { params[p.name] = Boolean(raw); continue; }
      const n = Number(raw);
      if (raw === "" || Number.isNaN(n) || (p.type === "int" && !Number.isInteger(n))) errs[`parameters.${p.name}`] = p.type === "int" ? "Enter a whole number." : "Enter a number.";
      else if ((p.minimum !== null && n < p.minimum) || (p.maximum !== null && n > p.maximum)) errs[`parameters.${p.name}`] = `Between ${p.minimum} and ${p.maximum}.`;
      else params[p.name] = n;
    }
    const timeout = Number(values.timeout), attempts = Number(values.attempts);
    if (!Number.isInteger(timeout) || timeout < 5 || timeout > 3600) errs.timeout = "5 to 3600 seconds.";
    if (!Number.isInteger(attempts) || attempts < 1 || attempts > 10) errs.attempts = "1 to 10 attempts.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setFormError(null);
    update.mutate({ parameters: params, timeout_seconds: timeout, max_attempts: attempts }, {
      onSuccess: () => toast.success("Configuration saved", { description: "It applies to executions that start from now on." }),
      onError: (err) => {
        if (err instanceof ApiError) {
          setErrors(err.fieldErrors);
          setFormError(Object.keys(err.fieldErrors).length ? null : err.message);
        } else setFormError("Couldn't save the configuration.");
      },
    });
  };

  return (
    <form onSubmit={submit} noValidate>
      <Panel title="Parameters" description={readOnly ? "You can view the configuration; changing it needs the automation.workflows.manage permission." : "Thresholds and switches read by this workflow's conditions and steps."}
        footer={!readOnly && (
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" disabled={!dirty || update.isPending} onClick={() => { setValues(initial); setErrors({}); }}><RotateCcw /> Reset</Button>
            <Button type="submit" variant="primary" loading={update.isPending} disabled={!dirty}><Save /> Save configuration</Button>
          </div>
        )}>
        <div className="space-y-5 p-4">
          <FormAlert message={formError} />
          <div className="grid gap-5 md:grid-cols-2">
            {wf.parameters.map((p) => p.type === "bool" ? (
              <div key={p.name} className="flex items-start justify-between gap-4 rounded-[var(--radius-control)] border border-border p-3 md:col-span-2">
                <div><p className="text-small font-medium">{p.label}</p><p className="text-small text-fg-muted">{p.description}</p></div>
                <Switch checked={Boolean(values.params[p.name])} disabled={readOnly} label={p.label}
                  onCheckedChange={(v) => setValues((s) => ({ ...s, params: { ...s.params, [p.name]: v } }))} />
              </div>
            ) : (
              <FormField key={p.name} label={p.label} htmlFor={`param-${p.name}`} error={errors[`parameters.${p.name}`]}
                hint={`${p.description} Default ${p.default}${p.unit ? ` ${p.unit}` : ""}.`}>
                <div className="relative">
                  <Input inputMode="decimal" className="tabular pr-20" disabled={readOnly} value={String(values.params[p.name] ?? "")}
                    onChange={(e) => setValues((s) => ({ ...s, params: { ...s.params, [p.name]: e.target.value } }))} />
                  {p.unit && <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-small text-fg-muted">{p.unit}</span>}
                </div>
              </FormField>
            ))}
          </div>
          <div className="grid gap-5 border-t border-border-subtle pt-5 md:grid-cols-2">
            <FormField label="Time limit per attempt" htmlFor="wf-timeout" error={errors.timeout} hint="The step is rolled back and retried if it runs longer.">
              <div className="relative"><Input inputMode="numeric" className="tabular pr-20" disabled={readOnly} value={values.timeout}
                onChange={(e) => setValues((s) => ({ ...s, timeout: e.target.value }))} /><span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-small text-fg-muted">seconds</span></div>
            </FormField>
            <FormField label="Maximum attempts" htmlFor="wf-attempts" error={errors.attempts} hint="Transient failures are retried with exponential backoff.">
              <Input inputMode="numeric" className="tabular" disabled={readOnly} value={values.attempts} onChange={(e) => setValues((s) => ({ ...s, attempts: e.target.value }))} />
            </FormField>
          </div>
        </div>
      </Panel>
    </form>
  );
}
