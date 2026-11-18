import { CalendarCheck, Compass, Info, MessagesSquare, Wallet } from "lucide-react";
import { ContactBand } from "@/components/contact-band";
import { Reveal } from "@/components/motion";
import { PageHero, SectionHeading } from "@/components/ui";
import { ABOUT, COMPANY, pick } from "@/content/company";
import { useI18n } from "@/lib/i18n";

const SERVICE_ICONS = [Compass, Wallet, CalendarCheck, MessagesSquare];

/** About Us. Copy lives in content/company.ts and is placeholder text until the business approves it. */
export default function AboutPage() {
  const { t, lang } = useI18n();
  return (
    <>
      <PageHero eyebrow={t("About Us", "من نحن")} title={t("Homes, chosen with clear information.", "منازل تُختار بمعلومات واضحة.")} lead={pick(ABOUT.intro, lang)}>
        <p role="note" className="mt-8 inline-flex items-start gap-2 rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-caption text-fg-muted">
          <Info className="mt-px size-3.5 shrink-0" aria-hidden />
          {t("Prototype website: company details on this page are placeholder text and the projects shown are fictional demo data.",
            "موقع تجريبي: بيانات الشركة في هذه الصفحة نصوص مؤقتة، والمشاريع المعروضة بيانات تجريبية وهمية.")}
        </p>
      </PageHero>

      {/* About + image */}
      <section aria-labelledby="about-smartestate">
        <div className="container-site grid gap-10 py-16 sm:py-24 lg:grid-cols-[1.1fr_1fr] lg:items-center">
          <Reveal><SectionHeading id="about-smartestate" eyebrow={t("About SmartEstate", "عن SmartEstate")}
            title={t("A simpler way from listing to viewing.", "طريق أبسط من العرض إلى الزيارة.")} lead={pick(COMPANY.summary, lang)} /></Reveal>
          <Reveal variant="image" delay={120} className="overflow-hidden rounded-[22px] shadow-[var(--shadow-card)]">
            <img src="/images/villa-rear.webp" alt={t("Architectural render of a modern villa's garden side with a pool", "تصوّر معماري للواجهة الخلفية لفيلا حديثة مع مسبح")}
              loading="lazy" className="aspect-[4/3] w-full object-cover object-[50%_85%]" />
          </Reveal>
        </div>
      </section>

      {/* Mission & vision */}
      <section className="border-y border-border bg-surface-subtle" aria-label={t("Mission and vision", "الرسالة والرؤية")}>
        <div className="container-site grid gap-6 py-16 sm:py-20 md:grid-cols-2">
          {[[t("Our mission", "رسالتنا"), pick(ABOUT.mission, lang)], [t("Our vision", "رؤيتنا"), pick(ABOUT.vision, lang)]].map(([title, text], i) => (
            <Reveal key={title} delay={i * 140} className="rounded-[var(--radius-panel)] border border-border bg-surface p-8 sm:p-10">
              <p className="eyebrow">{title}</p>
              <p className="mt-4 font-display text-[24px] leading-snug tracking-[-0.01em] text-fg sm:text-[28px]">{text}</p>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Approach */}
      <section aria-labelledby="approach-heading">
        <div className="container-site py-16 sm:py-24">
          <Reveal><SectionHeading id="approach-heading" eyebrow={t("Our approach", "نهجنا")} title={t("How we work with buyers.", "كيف نعمل مع المشترين.")} /></Reveal>
          <ol className="mt-12 grid gap-8 md:grid-cols-3">
            {ABOUT.approach.map((a, i) => (
              <Reveal as="li" key={a.title.en} delay={i * 140} className="border-t border-border-strong pt-6">
                <span className="font-display text-[40px] font-semibold leading-none text-brand/80">{String(i + 1).padStart(2, "0")}</span>
                <h3 className="mt-4 text-[18px] font-semibold">{pick(a.title, lang)}</h3>
                <p className="mt-2 text-body leading-6 text-fg-secondary">{pick(a.text, lang)}</p>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      {/* Services */}
      <section className="bg-surface-subtle" aria-labelledby="services-heading">
        <div className="container-site py-16 sm:py-24">
          <Reveal><SectionHeading id="services-heading" eyebrow={t("Our services", "خدماتنا")} title={t("What you can do with SmartEstate.", "ما يمكنك فعله مع SmartEstate.")} align="center" /></Reveal>
          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {ABOUT.services.map((s, i) => {
              const Icon = SERVICE_ICONS[i] ?? Compass;
              return (
                <Reveal key={s.title.en} delay={i * 110} className="rounded-[var(--radius-panel)] border border-border bg-surface p-7 shadow-[var(--shadow-card)] transition-[transform,box-shadow] duration-500 ease-[var(--ease-out-soft)] hover:-translate-y-1 hover:shadow-[var(--shadow-lift)]">
                  <span className="grid size-11 place-items-center rounded-full bg-brand-subtle text-brand"><Icon className="size-5" aria-hidden /></span>
                  <h3 className="mt-5 font-display text-[20px] font-semibold">{pick(s.title, lang)}</h3>
                  <p className="mt-2 text-body leading-6 text-fg-secondary">{pick(s.text, lang)}</p>
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      <div className="pt-16 sm:pt-24"><ContactBand /></div>
    </>
  );
}
