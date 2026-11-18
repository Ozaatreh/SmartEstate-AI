import { ArrowRight, Building2, MapPin } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui";
import type { PublicProject, PublicUnit } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { type Lang, useI18n } from "@/lib/i18n";
import { unitTypeLabel } from "@/lib/status";
import { cn } from "@/lib/utils";

export function bedroomsLabel(n: number, lang: Lang = "en"): string {
  if (lang === "ar") return n === 0 ? "استوديو" : n === 1 ? "غرفة نوم واحدة" : n === 2 ? "غرفتا نوم" : `${n} غرف نوم`;
  return n === 0 ? "Studio" : `${n} bedroom${n === 1 ? "" : "s"}`;
}

/**
 * Cover image when the project has a valid one; otherwise a quiet branded panel (never stock or invented imagery).
 * The API only offers image links as covers; if one still fails to load (moved, offline), the panel replaces it
 * instead of a broken-image icon. `note` adds a short caption to the panel (used on the project page hero).
 */
export function ProjectCover({ project, className = "aspect-[16/10]", note = false, imgClassName }: {
  project: Pick<PublicProject, "name" | "cover_image">; className?: string; note?: boolean; imgClassName?: string;
}) {
  const [failed, setFailed] = React.useState<string | null>(null);
  const { t } = useI18n();
  const src = project.cover_image;
  if (src && failed !== src) {
    return <img src={src} alt={note ? project.name : ""} className={cn(className, "w-full object-cover", imgClassName)} loading="lazy" onError={() => setFailed(src)} />;
  }
  return (
    <div className={`${className} relative grid w-full place-items-center overflow-hidden bg-[linear-gradient(135deg,var(--brand-subtle),var(--surface-sunken))]`}
      data-testid="cover-placeholder" aria-hidden={!note} role={note ? "img" : undefined} aria-label={note ? `${project.name} — ${t("images coming soon", "الصور قريباً")}` : undefined}>
      <div className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(var(--text)_1px,transparent_1px),linear-gradient(90deg,var(--text)_1px,transparent_1px)] [background-size:32px_32px]" />
      <div className="relative space-y-2 text-center">
        <Building2 className="mx-auto size-10 text-brand/60" aria-hidden />
        {note && <p className="text-small font-medium text-fg-secondary">{t("Project images coming soon", "صور المشروع قريباً")}</p>}
      </div>
    </div>
  );
}

/** Verified figures for a project card: starting price, homes available, handover (only those the API returns). */
function ProjectFacts({ p, className }: { p: PublicProject; className?: string }) {
  const { t } = useI18n();
  const facts = [
    { label: t("Starting from", "تبدأ من"), value: p.price_from_sar ? formatMoney(p.price_from_sar) : t("On request", "عند الطلب") },
    { label: t("Available", "المتاح"), value: t(`${p.available_units} ${p.available_units === 1 ? "home" : "homes"}`, `${p.available_units} ${p.available_units === 1 ? "وحدة" : "وحدات"}`) },
    ...(p.handover_date ? [{ label: t("Handover", "التسليم"), value: formatDate(p.handover_date) }] : []),
  ];
  return (
    <dl className={cn("grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3", className)}>
      {facts.map((f) => (
        <div key={f.label}>
          <dt className="text-caption uppercase tracking-[0.12em] text-fg-muted">{f.label}</dt>
          <dd className="mt-1 text-body font-semibold tabular text-fg">{f.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Project card. `layout="feature"` is a wide, two-column card used when a single project is highlighted, so a list
 * with one project still looks intentional.
 */
export function ProjectCard({ project: p, layout = "card" }: { project: PublicProject; layout?: "card" | "feature" }) {
  const feature = layout === "feature";
  const { t } = useI18n();
  return (
    <Link to={`/projects/${p.code}`}
      className={cn("group grid overflow-hidden rounded-[var(--radius-panel)] border border-border bg-surface shadow-[var(--shadow-card)] transition-[box-shadow,border-color,transform] duration-500 ease-[var(--ease-out-soft)] hover:-translate-y-1 hover:border-brand/40 hover:shadow-[var(--shadow-lift)] motion-reduce:hover:translate-y-0",
        feature && "md:grid-cols-[1.25fr_1fr]")}>
      <div className="relative overflow-hidden">
        <ProjectCover project={p} className={feature ? "aspect-[16/10] md:aspect-auto md:h-full md:min-h-[360px]" : "aspect-[4/3]"}
          imgClassName="transition-transform duration-[1200ms] ease-[var(--ease-out-soft)] group-hover:scale-[1.05] motion-reduce:transition-none motion-reduce:group-hover:scale-100" />
        <span className="absolute start-4 top-4"><StatusBadge status={p.status} /></span>
      </div>
      <div className={cn("flex flex-col p-6", feature && "md:justify-center md:p-10")}>
        <p className="flex items-center gap-1.5 text-small text-fg-muted"><MapPin className="size-3.5" aria-hidden />{[p.district, p.city].filter(Boolean).join(", ")}</p>
        <h3 className={cn("mt-2 font-display font-semibold tracking-[-0.015em] text-fg transition-colors group-hover:text-brand", feature ? "text-[30px] leading-tight sm:text-[36px]" : "text-[24px] leading-tight")}>
          {p.name}
        </h3>
        <ProjectFacts p={p} className="mt-6 border-t border-border-subtle pt-5" />
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          {p.is_demo_data ? <Badge tone="neutral">{t("Fictional demo data", "بيانات تجريبية وهمية")}</Badge> : <span />}
          <span className="inline-flex items-center gap-1.5 text-small font-medium text-brand">{t("View project", "عرض المشروع")} <ArrowRight className="size-4 transition-transform duration-500 ease-[var(--ease-out-soft)] group-hover:translate-x-1 rtl:-scale-x-100 rtl:group-hover:-translate-x-1" aria-hidden /></span>
        </div>
      </div>
    </Link>
  );
}

export function UnitRow({ unit: u }: { unit: PublicUnit }) {
  const { t, lang } = useI18n();
  return (
    <li>
      <Link to={`/projects/${u.project_code}/units/${u.code}`}
        className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-control)] border border-border bg-surface px-4 py-3.5 transition-colors hover:border-brand/50">
        <div className="min-w-0">
          <p className="text-body font-semibold tabular">{t("Unit", "الوحدة")} {u.code}</p>
          <p className="text-small text-fg-secondary">
            {u.type === "studio" ? unitTypeLabel("studio", lang) : `${unitTypeLabel(u.type, lang)} · ${bedroomsLabel(u.bedrooms, lang)}`} · {Number(u.area_sqm).toFixed(0)} {t("m²", "م²")} · {t("Floor", "الطابق")} {u.floor}{u.view ? ` · ${u.view}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-body font-semibold tabular">{formatMoney(u.list_price_sar)}</span>
          <StatusBadge status={u.status} />
        </div>
      </Link>
    </li>
  );
}
