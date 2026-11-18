import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Building2, CalendarCheck, Compass, Info, LayoutGrid, MessagesSquare, Wallet } from "lucide-react";
import type * as React from "react";
import { Link } from "react-router-dom";
import { ContactBand } from "@/components/contact-band";
import { ProjectCard } from "@/components/listing";
import { Reveal, StaggerWords, useParallax } from "@/components/motion";
import { buttonClass, DemoDataNote, ErrorNotice, SectionHeading, Skeleton } from "@/components/ui";
import { ABOUT, COMPANY, pick } from "@/content/company";
import { InteractivePropertyViewer } from "@/features/property-viewer/interactive-property-viewer";
import { SHOWCASES } from "@/features/property-viewer/showcases";
import { api, type PublicProject } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** What the platform actually offers (each one is a working feature of this website). */
const VALUES = [
  {
    icon: Building2,
    title: { en: "Premium Residential Communities", ar: "مجتمعات سكنية مميزة" },
    text: { en: "Explore published projects with their amenities, the units available today and an interactive 3D architectural model.", ar: "استكشف المشاريع المنشورة ومرافقها والوحدات المتاحة اليوم، مع نموذج معماري تفاعلي ثلاثي الأبعاد." },
  },
  {
    icon: Wallet,
    title: { en: "Flexible Payment Plans", ar: "خطط دفع مرنة" },
    text: { en: "See the payment plans offered for each project — down payment, instalments and handover share — before you speak to anyone.", ar: "اطّلع على خطط الدفع المتاحة لكل مشروع — الدفعة الأولى والأقساط ونسبة التسليم — قبل أن تتحدث مع أحد." },
  },
  {
    icon: MessagesSquare,
    title: { en: "Personalized Property Support", ar: "دعم عقاري شخصي" },
    text: { en: "Request a viewing or send a question and our sales team follows up; our assistant answers from the live listings.", ar: "اطلب زيارة أو أرسل سؤالك وسيتابع معك فريق المبيعات، ويجيب مساعدنا من العروض الحالية." },
  },
];

const STEPS = [
  { icon: Compass, title: { en: "Discover projects", ar: "اكتشف المشاريع" }, text: { en: "Browse our residential projects, their locations and amenities.", ar: "تصفّح مشاريعنا السكنية ومواقعها ومرافقها." } },
  { icon: LayoutGrid, title: { en: "Explore available properties", ar: "استكشف الوحدات المتاحة" }, text: { en: "Compare available units by size, floor and price, with their payment plans.", ar: "قارن الوحدات المتاحة حسب المساحة والطابق والسعر، مع خطط الدفع." } },
  { icon: CalendarCheck, title: { en: "Contact our team", ar: "تواصل مع فريقنا" }, text: { en: "Request a viewing or send a message — an advisor will get in touch.", ar: "اطلب زيارة أو أرسل رسالة — وسيتواصل معك أحد المستشارين." } },
];

const ARROW = "rtl:-scale-x-100";

export default function HomePage() {
  const { t, lang } = useI18n();
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api.get<PublicProject[]>("/projects") });
  const showcaseProject = projects.data?.find((p) => SHOWCASES[p.code]);
  const showcase = showcaseProject ? SHOWCASES[showcaseProject.code] : undefined;
  const parallax = useParallax<HTMLImageElement>(22);
  const headline = t("Discover a Better Way to Find Your Next Home.", "اكتشف طريقة أفضل للعثور على منزلك القادم.");
  const after = 120 + headline.split(" ").length * 70; // the rest of the hero follows the headline
  const d = (ms: number) => ({ "--d": `${ms}ms` }) as React.CSSProperties;

  return (
    <>
      {/* 1 · Hero */}
      <section className="relative overflow-hidden border-b border-border">
        <div className="container-site grid items-center gap-10 py-14 sm:py-20 lg:grid-cols-[1fr_1.1fr] lg:gap-14 lg:py-24">
          <div>
            <p className="eyebrow enter-fade">{t("Residential projects · Saudi Arabia", "مشاريع سكنية · المملكة العربية السعودية")}</p>
            <h1 className="mt-4 font-display text-[40px] font-semibold leading-[1.06] tracking-[-0.03em] sm:text-[52px] lg:text-hero">
              <StaggerWords text={headline} start={120} />
            </h1>
            <p className="enter-up mt-6 max-w-xl text-[17px] leading-8 text-fg-secondary" style={d(after)}>{pick(ABOUT.intro, lang)}</p>
            <div className="enter-up mt-8 flex flex-wrap gap-3" style={d(after + 140)}>
              <Link to="/projects" className={buttonClass("brand", "lg")}>{t("Explore Projects", "استكشف المشاريع")} <ArrowRight className={ARROW} /></Link>
              <Link to="/about" className={buttonClass("secondary", "lg")}>{t("About Us", "من نحن")}</Link>
            </div>
            <div className="enter-fade" style={d(after + 300)}><DemoDataNote className="mt-8" /></div>
          </div>
          <figure className="relative">
            <div className="enter-reveal overflow-hidden rounded-[22px] shadow-[var(--shadow-lift)]" style={d(150)}>
              <img ref={parallax} src="/images/villa-hero.webp"
                alt={t("Architectural render of a modern two-storey villa with glazed facades and landscaped gardens", "تصوّر معماري لفيلا حديثة من طابقين بواجهات زجاجية وحدائق منسّقة")}
                className="aspect-[4/3] w-full scale-[1.06] object-cover will-change-transform sm:aspect-[16/11]" fetchPriority="high" />
            </div>
            <figcaption style={d(1100)} className="enter-fade absolute bottom-4 start-4 inline-flex items-center gap-1.5 rounded-full bg-black/55 px-3 py-1.5 text-caption text-white backdrop-blur-sm">
              <Info className="size-3.5" aria-hidden /> {t("Illustrative architectural render", "تصوّر معماري توضيحي")}
            </figcaption>
            <div className="pointer-events-none absolute -bottom-6 -end-6 -z-10 hidden size-40 rounded-[22px] bg-brand-subtle lg:block" aria-hidden />
          </figure>
        </div>
      </section>

      {/* 2 · Value proposition */}
      <section className="bg-surface-subtle" aria-labelledby="values-heading">
        <div className="container-site py-16 sm:py-24">
          <Reveal><SectionHeading id="values-heading" eyebrow={t("Why SmartEstate", "لماذا SmartEstate")} align="center"
            title={t("Everything you need to choose with confidence.", "كل ما تحتاجه لتختار بثقة.")} /></Reveal>
          <div className="mt-12 grid gap-px overflow-hidden rounded-[var(--radius-panel)] border border-border bg-border md:grid-cols-3">
            {VALUES.map((v, i) => (
              <Reveal key={v.title.en} delay={i * 120} className="group bg-surface p-8">
                <span className="grid size-11 place-items-center rounded-full bg-brand-subtle text-brand transition-transform duration-500 ease-[var(--ease-out-soft)] group-hover:-translate-y-0.5"><v.icon className="size-5" aria-hidden /></span>
                <h3 className="mt-6 font-display text-[22px] font-semibold leading-tight tracking-[-0.01em]">{pick(v.title, lang)}</h3>
                <p className="mt-3 text-body leading-6 text-fg-secondary">{pick(v.text, lang)}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* 3 · Featured projects */}
      <section aria-labelledby="projects-heading">
        <div className="container-site py-16 sm:py-24">
          <Reveal className="flex flex-wrap items-end justify-between gap-4">
            <SectionHeading id="projects-heading" eyebrow={t("Featured projects", "مشاريع مميزة")} title={t("Communities open for sale", "مجتمعات متاحة للبيع")}
              lead={t("Live availability and starting prices, straight from our sales system.", "الوحدات المتاحة والأسعار المبدئية، مباشرة من نظام المبيعات.")} />
            <Link to="/projects" className="inline-flex items-center gap-1.5 text-body font-medium text-brand hover:underline">
              {t("All projects", "كل المشاريع")} <ArrowRight className={`size-4 ${ARROW}`} aria-hidden />
            </Link>
          </Reveal>
          <div className="mt-10">
            {projects.isPending ? <Skeleton className="h-[420px] rounded-[var(--radius-panel)]" />
              : projects.isError ? <ErrorNotice message={t("We couldn't load our projects right now.", "تعذّر تحميل المشاريع حالياً.")} onRetry={() => void projects.refetch()} />
                : projects.data.length === 1 ? <Reveal><ProjectCard project={projects.data[0]!} layout="feature" /></Reveal>
                  : projects.data.length ? <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{projects.data.slice(0, 3).map((p, i) => <Reveal key={p.code} delay={i * 120}><ProjectCard project={p} /></Reveal>)}</div>
                    : <p className="text-body text-fg-muted">{t("New projects are coming soon.", "مشاريع جديدة قريباً.")} <Link className="text-brand hover:underline" to="/contact">{t("Contact us", "تواصل معنا")}</Link></p>}
          </div>
        </div>
      </section>

      {/* 4 · How it works */}
      <section className="border-y border-border bg-surface-subtle" aria-labelledby="steps-heading">
        <div className="container-site py-16 sm:py-24">
          <Reveal><SectionHeading id="steps-heading" eyebrow={t("How it works", "كيف تعمل")} title={t("From first look to viewing in three steps.", "من النظرة الأولى إلى الزيارة في ثلاث خطوات.")} /></Reveal>
          <ol className="mt-12 grid gap-8 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <Reveal as="li" key={s.title.en} delay={i * 140} className="relative border-t border-border-strong pt-6">
                <span className="font-display text-[44px] font-semibold leading-none text-brand/80">{String(i + 1).padStart(2, "0")}</span>
                <h3 className="mt-4 flex items-center gap-2 text-[18px] font-semibold"><s.icon className="size-5 text-brand" aria-hidden />{pick(s.title, lang)}</h3>
                <p className="mt-2 text-body leading-6 text-fg-secondary">{pick(s.text, lang)}</p>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      {/* 5 · Featured 3D experience (only while the showcased project is published) */}
      {showcase && showcaseProject && (
        <section className="bg-[#111214] text-white" aria-labelledby="home-3d-heading">
          <div className="container-site py-16 sm:py-24">
            <Reveal className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
              <div className="max-w-2xl">
                <p className="text-eyebrow font-semibold uppercase tracking-[0.18em] text-[#d39a72]">{t("Explore in 3D", "استكشف بتقنية ثلاثية الأبعاد")}</p>
                <h2 id="home-3d-heading" className="mt-3 font-display text-[30px] font-semibold leading-[1.15] tracking-[-0.02em] sm:text-[40px]">
                  {t("Walk around the architecture, from every angle.", "تجوّل حول التصميم المعماري من كل زاوية.")}
                </h2>
                <p className="mt-4 text-lead text-white/70 sm:text-[17px] sm:leading-7">
                  {t(`Rotate, zoom and view the building in full screen — an interactive architectural model shown with ${showcaseProject.name}.`,
                    `دوّر المبنى وقرّبه واعرضه بملء الشاشة — نموذج معماري تفاعلي يُعرض مع ${showcaseProject.name}.`)}
                </p>
              </div>
              <Link to={`/projects/${showcaseProject.code}`} className={buttonClass("onDark", "lg")}>
                {t(`View ${showcaseProject.name}`, `عرض ${showcaseProject.name}`)} <ArrowRight className={ARROW} />
              </Link>
            </Reveal>
            <Reveal variant="fade" delay={150}><InteractivePropertyViewer className="mt-10" modelUrl={showcase.modelUrl} posterUrl={showcase.posterUrl} title={showcaseProject.name} camera={showcase.camera} /></Reveal>
            <p className="mt-4 flex items-start gap-2 text-small text-white/65" data-testid="home-3d-notice"><Info className="mt-0.5 size-4 shrink-0" aria-hidden />{pick(showcase.notice, lang)}</p>
          </div>
        </section>
      )}

      {/* 6 · About */}
      <section aria-labelledby="about-heading">
        <div className="container-site grid gap-10 py-16 sm:py-24 lg:grid-cols-[1fr_1fr] lg:items-center">
          <Reveal variant="image" className="overflow-hidden rounded-[22px]">
            <img src="/images/villa-side.webp" alt={t("Architectural render of a villa seen from the side, with terraces and planting", "تصوّر معماري لفيلا من الجانب مع شرفات ونباتات")}
              loading="lazy" className="aspect-[4/3] w-full object-cover object-[50%_85%]" />
          </Reveal>
          <Reveal delay={150}>
            <SectionHeading id="about-heading" eyebrow={t("About SmartEstate", "عن SmartEstate")} title={t("Clear information, and people who follow up.", "معلومات واضحة، وفريق يتابع معك.")}
              lead={pick(COMPANY.summary, lang)} />
            <p className="mt-4 text-body leading-7 text-fg-secondary">{pick(ABOUT.mission, lang)}</p>
            <Link to="/about" className={buttonClass("secondary", "lg", "mt-8")}>{t("More about us", "المزيد عنّا")} <ArrowRight className={ARROW} /></Link>
          </Reveal>
        </div>
      </section>

      {/* 7 · Contact CTA */}
      <ContactBand />
    </>
  );
}
