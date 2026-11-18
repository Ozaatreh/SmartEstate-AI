import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, Check, MapPin } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { bedroomsLabel, ProjectCard, ProjectCover, UnitRow } from "@/components/listing";
import { Badge, buttonClass, DemoDataNote, ErrorNotice, PageHero, Select, Skeleton, StatusBadge } from "@/components/ui";
import { Reveal } from "@/components/motion";
import { ProjectLocation } from "@/features/location/project-location";
import { ModelSection } from "@/features/model-viewer/model-section";
import { Explore3DSection, type ExploreLink } from "@/features/property-viewer/explore-3d-section";
import { SHOWCASES } from "@/features/property-viewer/showcases";
import { api, ApiError, type PublicProject, type PublicProjectDetail, type PublicUnit, type PublicUnitDetail } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { frequencyLabel, unitTypeLabel } from "@/lib/status";
import NotFoundPage from "./not-found";

export function ProjectsPage() {
  const { t } = useI18n();
  const q = useQuery({ queryKey: ["projects"], queryFn: () => api.get<PublicProject[]>("/projects") });
  return (
    <>
      <PageHero eyebrow={t("Projects", "المشاريع")} title={t("Communities open for sale", "مجتمعات متاحة للبيع")}
        lead={t("Live availability, starting prices and handover dates — straight from our sales system.", "الوحدات المتاحة والأسعار المبدئية ومواعيد التسليم — مباشرة من نظام المبيعات.")}>
        <DemoDataNote className="mt-6" />
      </PageHero>
      <div className="container-site py-12 sm:py-16">
        {q.isPending ? <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-[420px] rounded-[var(--radius-panel)]" />)}</div>
          : q.isError ? <ErrorNotice message={t("We couldn't load our projects right now.", "تعذّر تحميل المشاريع حالياً.")} onRetry={() => void q.refetch()} />
            : q.data.length === 1 ? <Reveal><ProjectCard project={q.data[0]!} layout="feature" /></Reveal>
              : q.data.length ? <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{q.data.map((p, i) => <Reveal key={p.code} delay={(i % 3) * 120}><ProjectCard project={p} /></Reveal>)}</div>
                : <p className="text-body text-fg-muted">{t("No projects are open for sale right now.", "لا توجد مشاريع متاحة للبيع حالياً.")}</p>}
      </div>
    </>
  );
}

export function ProjectPage() {
  const { code = "" } = useParams();
  const { t, lang } = useI18n();
  const project = useQuery({ queryKey: ["project", code], queryFn: () => api.get<PublicProjectDetail>(`/projects/${encodeURIComponent(code)}`), retry: false });
  const [bedrooms, setBedrooms] = React.useState("");
  const units = useQuery({
    queryKey: ["units", code, bedrooms],
    queryFn: () => api.get<PublicUnit[]>(`/projects/${encodeURIComponent(code)}/units`, { bedrooms: bedrooms || null }),
    enabled: project.isSuccess,
  });
  if (project.isError && project.error instanceof ApiError && project.error.status === 404) return <NotFoundPage what="project" />;
  if (project.isError) return <div className="container-site py-12"><ErrorNotice message={t("We couldn't load this project.", "تعذّر تحميل هذا المشروع.")} onRetry={() => void project.refetch()} /></div>;
  if (project.isPending) return <div className="container-site space-y-4 py-12"><Skeleton className="h-10 w-80" /><Skeleton className="h-72" /></div>;
  const p = project.data;
  const showcase = SHOWCASES[p.code];
  const viewingHref = `/request-viewing?project=${encodeURIComponent(p.code)}`;
  const exploreLinks: ExploreLink[] = [
    ...(p.description ? [{ label: t("Project overview", "نظرة عامة على المشروع"), href: "#overview" }] : []),
    ...(p.amenities.length ? [{ label: t("Amenities", "المرافق"), href: "#amenities" }] : []),
    { label: t("Available units", "الوحدات المتاحة"), href: "#units" },
    { label: t("Request information", "اطلب معلومات"), href: viewingHref },
  ];

  return (
    <div className="container-site py-8 sm:py-10">
      {/* 1 · Title, location, status */}
      <nav aria-label={t("Breadcrumb", "مسار التنقل")} className="mb-5 text-small text-fg-muted"><Link to="/projects" className="hover:text-fg">{t("Projects", "المشاريع")}</Link> <span aria-hidden>/</span> {p.name}</nav>
      <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="eyebrow">{p.city}</p>
          <h1 className="mt-2 font-display text-[38px] font-semibold leading-[1.08] tracking-[-0.025em] sm:text-[52px]">{p.name}</h1>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-small text-fg-secondary">
            <StatusBadge status={p.status} />
            <span className="flex items-center gap-1"><MapPin className="size-3.5" aria-hidden />{[p.district, p.city].filter(Boolean).join(", ")}</span>
            {p.handover_date && <span>{t("Handover", "التسليم")} {formatDate(p.handover_date)}</span>}
            {p.is_demo_data && <Badge>{t("Fictional demo data", "بيانات تجريبية وهمية")}</Badge>}
          </div>
        </div>
        <Link to={viewingHref} className={buttonClass("brand", "lg")}><CalendarCheck /> {t("Request a Viewing", "اطلب زيارة")}</Link>
      </div>

      {/* 2 · Hero image */}
      <div className="enter-reveal mt-8 overflow-hidden rounded-[22px] border border-border shadow-[var(--shadow-card)]" style={{ "--d": "120ms" } as React.CSSProperties}><ProjectCover project={p} className="aspect-[16/9] sm:aspect-[21/9]" note /></div>

      {/* 3 · Interactive 3D viewer */}
      {showcase && <Reveal variant="fade"><Explore3DSection projectName={p.name} showcase={showcase} links={exploreLinks} /></Reveal>}

      {/* 4 · Overview · 5 · Amenities */}
      {(p.description || p.amenities.length > 0) && (
        <Reveal className="mt-14 grid gap-10 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          {p.description ? (
            <section id="overview" className="scroll-mt-24" aria-labelledby="overview-heading">
              <p className="eyebrow">{t("Overview", "نظرة عامة")}</p>
              <h2 id="overview-heading" className="mt-2 font-display text-[28px] font-semibold tracking-[-0.015em]">{t(`About ${p.name}`, `عن ${p.name}`)}</h2>
              <p className="mt-4 whitespace-pre-line text-[17px] leading-8 text-fg-secondary">{p.description}</p>
            </section>
          ) : <div />}
          {p.amenities.length > 0 && (
            <section id="amenities" className="scroll-mt-24 rounded-[var(--radius-panel)] border border-border bg-surface p-6 shadow-[var(--shadow-card)]" aria-labelledby="amenities-heading">
              <h2 id="amenities-heading" className="font-display text-[22px] font-semibold">{t("Amenities", "المرافق")}</h2>
              <ul className="mt-4 grid gap-2.5 text-body sm:grid-cols-2 lg:grid-cols-1">
                {p.amenities.map((a) => <li key={a} className="flex items-center gap-2.5"><Check className="size-4 shrink-0 text-success" aria-hidden />{a}</li>)}
              </ul>
            </section>
          )}
        </Reveal>
      )}

      {/* 6 · Available units */}
      <section id="units" aria-labelledby="units-heading" className="mt-14 scroll-mt-24">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow">{t("Availability", "التوفّر")}</p>
            <h2 id="units-heading" className="mt-2 font-display text-[28px] font-semibold tracking-[-0.015em]">{t("Available units", "الوحدات المتاحة")}</h2>
            <p className="mt-1 text-small text-fg-muted">{t(`${p.available_units} available`, `${p.available_units} متاحة`)}{p.price_from_sar ? ` · ${t("from", "تبدأ من")} ${formatMoney(p.price_from_sar)}` : ""}</p>
          </div>
          {p.bedroom_options.length > 1 && (
            <label className="flex items-center gap-2 text-small">{t("Bedrooms", "غرف النوم")}
              <Select className="h-9 w-40" value={bedrooms} onChange={(e) => setBedrooms(e.target.value)}>
                <option value="">{t("Any", "الكل")}</option>
                {p.bedroom_options.map((b) => <option key={b} value={b}>{bedroomsLabel(b, lang)}</option>)}
              </Select>
            </label>
          )}
        </div>
        {units.isPending ? <Skeleton className="h-40" /> : units.isError ? <ErrorNotice message={t("We couldn't load the units.", "تعذّر تحميل الوحدات.")} onRetry={() => void units.refetch()} />
          : units.data.length ? <ul className="grid gap-2 lg:grid-cols-2">{units.data.map((u) => <UnitRow key={u.code} unit={u} />)}</ul>
            : <p className="text-body text-fg-muted">{t("No units match right now.", "لا توجد وحدات مطابقة حالياً.")} <Link to={viewingHref} className="text-brand hover:underline">{t("Ask us about upcoming releases.", "اسألنا عن الإصدارات القادمة.")}</Link></p>}
      </section>

      {/* 7 · Payment plans */}
      {p.payment_plans.length > 0 && (
        <Reveal as="section" className="mt-14" aria-labelledby="plans-heading">
          <p className="eyebrow">{t("Payment plans", "خطط الدفع")}</p>
          <h2 id="plans-heading" className="mt-2 font-display text-[28px] font-semibold tracking-[-0.015em]">{t("Ways to pay", "طرق الدفع")}</h2>
          <ul className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {p.payment_plans.map((pl) => (
              <li key={pl.name} className="rounded-[var(--radius-panel)] border border-border bg-surface p-6 shadow-[var(--shadow-card)]">
                <p className="font-display text-[20px] font-semibold">{pl.name}</p>
                <p className="mt-2 text-body leading-6 text-fg-secondary">
                  {t(`${Number(pl.down_payment_pct)}% down · ${pl.installments} ${frequencyLabel(pl.installment_frequency)} installments`,
                    `${Number(pl.down_payment_pct)}% دفعة أولى · ${pl.installments} أقساط ${frequencyLabel(pl.installment_frequency, "ar")}`)}
                  {Number(pl.handover_pct) > 0 ? t(` · ${Number(pl.handover_pct)}% on handover`, ` · ${Number(pl.handover_pct)}% عند التسليم`) : ""}
                </p>
              </li>
            ))}
          </ul>
        </Reveal>
      )}

      {/* Approved 3D models from the dashboard (Phase 7), when there are any */}
      {p.models.length > 0 && <div className="mt-14"><ModelSection models={p.models} isDemo={p.is_demo_data} enquireHref={viewingHref} heading={t("3D model", "النموذج ثلاثي الأبعاد")} /></div>}

      {/* 8 · Location */}
      <Reveal className="mt-14"><ProjectLocation location={p.location} projectName={p.name} projectCode={p.code} isDemo={p.is_demo_data} lang={lang} /></Reveal>

      {/* 9 · Request a viewing */}
      <Reveal as="section" className="mt-14 flex flex-col items-start justify-between gap-6 rounded-[22px] bg-surface-inverse px-6 py-10 text-white sm:flex-row sm:items-center sm:px-10" aria-labelledby="project-cta">
        <div>
          <h2 id="project-cta" className="font-display text-[26px] font-semibold tracking-[-0.015em] sm:text-[30px]">{t(`Interested in ${p.name}?`, `مهتم بـ ${p.name}؟`)}</h2>
          <p className="mt-2 max-w-xl text-body text-white/75">{t("Request a viewing and an advisor will confirm a time with you, or ask us anything about the available units.", "اطلب زيارة وسيؤكد أحد المستشارين الموعد معك، أو اسألنا عن أي شيء يخص الوحدات المتاحة.")}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link to={viewingHref} className={buttonClass("brand", "lg")}><CalendarCheck /> {t("Request a Viewing", "اطلب زيارة")}</Link>
          <Link to="/contact" className={buttonClass("onDark", "lg")}>{t("Contact us", "تواصل معنا")}</Link>
        </div>
      </Reveal>
    </div>
  );
}

export function UnitPage() {
  const { code = "", unit = "" } = useParams();
  const { t, lang } = useI18n();
  const q = useQuery({
    queryKey: ["unit", code, unit],
    queryFn: () => api.get<PublicUnitDetail>(`/projects/${encodeURIComponent(code)}/units/${encodeURIComponent(unit)}`),
    retry: false,
  });
  if (q.isError && q.error instanceof ApiError && q.error.status === 404) return <NotFoundPage what="unit" />;
  if (q.isError) return <div className="container-site max-w-5xl py-12"><ErrorNotice message={t("We couldn't load this unit.", "تعذّر تحميل هذه الوحدة.")} onRetry={() => void q.refetch()} /></div>;
  if (q.isPending) return <div className="mx-auto max-w-4xl space-y-4 px-4 py-12"><Skeleton className="h-10 w-64" /><Skeleton className="h-48" /></div>;
  const u = q.data;
  const facts = [
    [t("Type", "النوع"), unitTypeLabel(u.type, lang)], [t("Bedrooms", "غرف النوم"), bedroomsLabel(u.bedrooms, lang)], [t("Bathrooms", "دورات المياه"), String(u.bathrooms)],
    [t("Area", "المساحة"), `${Number(u.area_sqm).toFixed(0)} ${t("m²", "م²")}`], [t("Floor", "الطابق"), String(u.floor)], [t("View", "الإطلالة"), u.view ?? "—"],
  ];
  return (
    <div className="container-site max-w-5xl py-10">
      <nav aria-label={t("Breadcrumb", "مسار التنقل")} className="mb-4 text-small text-fg-muted">
        <Link to="/projects" className="hover:text-fg">{t("Projects", "المشاريع")}</Link> / <Link to={`/projects/${u.project_code}`} className="hover:text-fg">{u.project}</Link> / {t("Unit", "الوحدة")} {u.code}
      </nav>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-[36px] font-semibold leading-tight tracking-[-0.02em]">{t("Unit", "الوحدة")} {u.code}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-3"><StatusBadge status={u.status} />
            <span className="text-h3 font-semibold tabular">{formatMoney(u.list_price_sar)}</span>
            {u.project_is_demo_data && <Badge>{t("Fictional demo data", "بيانات تجريبية وهمية")}</Badge>}</div>
        </div>
        {u.status === "available" && (
          <Link to={`/request-viewing?project=${u.project_code}&unit=${u.code}`} className={buttonClass("brand", "lg")}><CalendarCheck /> {t("Request a viewing", "اطلب زيارة")}</Link>
        )}
      </div>
      <dl className="mt-8 grid grid-cols-2 gap-4 rounded-[var(--radius-panel)] border border-border bg-surface p-5 sm:grid-cols-3">
        {facts.map(([k, val]) => <div key={k}><dt className="text-small text-fg-muted">{k}</dt><dd className="text-body font-medium">{val}</dd></div>)}
      </dl>
      <div className="mt-8">
        <ModelSection models={u.models} isDemo={u.project_is_demo_data} heading={t("3D model of this unit", "النموذج ثلاثي الأبعاد لهذه الوحدة")}
          enquireHref={`/request-viewing?project=${u.project_code}&unit=${u.code}`} />
      </div>
      {u.payment_plans.length > 0 && (
        <section className="mt-8" aria-labelledby="plans-heading">
          <h2 id="plans-heading" className="mb-3 text-h3 font-semibold">{t("Payment plans for this unit", "خطط الدفع لهذه الوحدة")}</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {u.payment_plans.map((pl) => (
              <div key={pl.name} className="rounded-[var(--radius-panel)] border border-border bg-surface p-5">
                <p className="text-body font-semibold">{pl.name}</p>
                <dl className="mt-3 space-y-1.5 text-small">
                  <div className="flex justify-between"><dt className="text-fg-secondary">{t("Down payment", "الدفعة الأولى")} ({Number(pl.down_payment_pct)}%)</dt><dd className="tabular">{formatMoney(pl.down_payment_sar)}</dd></div>
                  {pl.installments > 0 && <div className="flex justify-between"><dt className="text-fg-secondary">{pl.installments} × {frequencyLabel(pl.installment_frequency, lang)}</dt><dd className="tabular">{formatMoney(pl.installment_amount_sar, { decimals: 2 })}</dd></div>}
                  {Number(pl.handover_pct) > 0 && <div className="flex justify-between"><dt className="text-fg-secondary">{t("On handover", "عند التسليم")} ({Number(pl.handover_pct)}%)</dt><dd className="tabular">{formatMoney(pl.handover_payment_sar)}</dd></div>}
                  <div className="flex justify-between border-t border-border-subtle pt-1.5 font-medium"><dt>{t("Total", "الإجمالي")}</dt><dd className="tabular">{formatMoney(pl.total_sar)}</dd></div>
                </dl>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
