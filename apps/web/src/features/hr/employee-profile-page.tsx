import { Briefcase, Building2, CalendarDays, ChevronUp, Mail, MapPin, Pencil, Phone, UserCheck, UserX } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Chip, StatusBadge } from "@/components/system/badges";
import { ConfirmDialog } from "@/components/system/forms";
import { DescriptionList, Panel } from "@/components/system/layout-blocks";
import { ErrorState, ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { Avatar, Skeleton } from "@/components/ui/primitives";
import { useCan } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api-client";
import { formatDate } from "@/lib/format";
import { useEmployee, useSaveEmployee, type EmployeeRef } from "./api";
import { EmployeeFormDialog } from "./employee-form-dialog";
import { initialsOf } from "@/lib/utils";

export default function EmployeeProfilePage() {
  const { id } = useParams();
  const q = useEmployee(id);
  const canManage = useCan("hr.employees.manage");
  const save = useSaveEmployee(id);
  const [editing, setEditing] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);

  if (q.isPending) return <ProfileSkeleton />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} className="min-h-[50vh]" />;
  const e = q.data;

  const toggleActive = () => save.mutate({ is_active: !e.is_active }, {
    onSuccess: () => { toast.success(e.is_active ? "Employee deactivated" : "Employee reactivated"); setConfirming(false); },
    onError: (err) => { toast.error(err instanceof ApiError ? err.message : "Couldn't update the employee"); setConfirming(false); },
  });

  return (
    <>
      <Link to="/hr/employees" className="mb-4 inline-flex items-center gap-1 text-small text-fg-muted hover:text-fg">← Employees</Link>
      <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <Avatar initials={initialsOf(e.full_name)} className="size-14 [&_span]:text-lead" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-h2 font-semibold tracking-[-0.015em]">{e.full_name}</h1>
              {!e.is_active && <StatusBadge status="inactive" />}
            </div>
            <p className="text-body text-fg-secondary">{e.job_title} · {e.department.name}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Chip>{e.employee_no}</Chip>
              {e.manages_departments.map((d) => <Chip key={d.id}>Manages {d.name}</Chip>)}
            </div>
          </div>
        </div>
        {canManage && (
          <div className="flex gap-2">
            <Button onClick={() => setEditing(true)}><Pencil /> Edit</Button>
            <Button variant={e.is_active ? "ghost" : "secondary"} onClick={() => setConfirming(true)}>
              {e.is_active ? <><UserX /> Deactivate</> : <><UserCheck /> Reactivate</>}
            </Button>
          </div>
        )}
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Profile" className="lg:col-span-2">
          <DescriptionList items={[
            { label: "Email", value: e.email ? <a className="inline-flex items-center gap-1.5 text-brand hover:underline" href={`mailto:${e.email}`}><Mail className="size-3.5" />{e.email}</a> : "—" },
            { label: "Phone", value: e.phone ? <span className="inline-flex items-center gap-1.5"><Phone className="size-3.5 text-fg-muted" />{e.phone}</span> : "—" },
            { label: "Department", value: <span className="inline-flex items-center gap-1.5"><Building2 className="size-3.5 text-fg-muted" />{e.department.name}</span> },
            { label: "Title", value: <span className="inline-flex items-center gap-1.5"><Briefcase className="size-3.5 text-fg-muted" />{e.job_title}</span> },
            { label: "Location", value: e.location ? <span className="inline-flex items-center gap-1.5"><MapPin className="size-3.5 text-fg-muted" />{e.location}</span> : "—" },
            { label: "Hire date", value: e.hire_date ? <span className="inline-flex items-center gap-1.5"><CalendarDays className="size-3.5 text-fg-muted" />{formatDate(e.hire_date)}</span> : "—" },
            { label: "System access", value: e.user ? <span>{e.user.email} · {e.user.roles.join(", ") || "No roles"}</span> : <span className="text-fg-muted">No user account</span> },
          ]} />
        </Panel>

        <div className="space-y-4">
          <Panel title="Reporting line" description={e.reporting_line.length ? `${e.reporting_line.length} level${e.reporting_line.length > 1 ? "s" : ""} up` : "Top of the organisation"}>
            <ol className="p-4">
              {[...e.reporting_line].reverse().map((m) => (
                <li key={m.id} className="flex flex-col items-start">
                  <PersonLink person={m} />
                  <ChevronUp className="my-1 ml-3 size-3.5 rotate-180 text-fg-muted" aria-hidden />
                </li>
              ))}
              <li className="flex items-center gap-2.5 rounded-[var(--radius-control)] bg-brand-subtle px-2 py-1.5">
                <Avatar initials={initialsOf(e.full_name)} className="size-7 [&_span]:text-[10px]" />
                <span className="text-body font-medium">{e.full_name}</span>
              </li>
            </ol>
          </Panel>
          <Panel title="Direct reports" description={e.direct_reports.length ? `${e.direct_reports.length} people` : undefined}>
            {e.direct_reports.length ? (
              <ul className="divide-y divide-border-subtle">{e.direct_reports.map((r) => <li key={r.id} className="px-4 py-2"><PersonLink person={r} /></li>)}</ul>
            ) : <p className="px-4 py-6 text-small text-fg-muted">No one reports to {e.full_name.split(" ")[0]}.</p>}
          </Panel>
        </div>
      </div>

      {canManage && <EmployeeFormDialog open={editing} onOpenChange={setEditing} employee={e} />}
      <ConfirmDialog open={confirming} onOpenChange={setConfirming} tone={e.is_active ? "danger" : "primary"} loading={save.isPending} onConfirm={toggleActive}
        title={e.is_active ? `Deactivate ${e.full_name}?` : `Reactivate ${e.full_name}?`}
        description={e.is_active ? "They disappear from the active directory and pickers. Their history is kept." : "They return to the active directory."}
        confirmLabel={e.is_active ? "Deactivate" : "Reactivate"} />
    </>
  );
}

function PersonLink({ person }: { person: EmployeeRef }) {
  return (
    <Link to={`/hr/employees/${person.id}`} className="group flex items-center gap-2.5 rounded-[var(--radius-control)] px-2 py-1.5 transition-colors hover:bg-surface-subtle">
      <Avatar initials={initialsOf(person.full_name)} className="size-7 [&_span]:text-[10px]" />
      <span className="min-w-0">
        <span className="block truncate text-body font-medium group-hover:text-brand">{person.full_name}</span>
        <span className="block truncate text-caption text-fg-muted">{person.job_title}</span>
      </span>
    </Link>
  );
}

function ProfileSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading profile">
      <div className="mb-6 flex items-center gap-4"><Skeleton className="size-14 rounded-full" /><div className="space-y-2"><Skeleton className="h-6 w-56" /><Skeleton className="h-4 w-40" /></div></div>
      <div className="grid gap-4 lg:grid-cols-3"><div className="rounded-[var(--radius-panel)] border border-border bg-surface lg:col-span-2"><ListSkeleton rows={5} /></div><div className="rounded-[var(--radius-panel)] border border-border bg-surface"><ListSkeleton rows={3} /></div></div>
    </div>
  );
}
