import { Clock, Info, MapPin, MessageSquareText } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHero } from "@/components/ui";
import { COMPANY, pick } from "@/content/company";
import { InquiryForm } from "@/features/inquiry/inquiry-form";
import { useI18n } from "@/lib/i18n";

const ICONS = { location: MapPin, hours: Clock, response: MessageSquareText };

/** Two columns: the inquiry form (unchanged behaviour and validation) and the company's contact details. */
function Shell({ eyebrow, title, intro, children }: { eyebrow: string; title: string; intro: string; children: React.ReactNode }) {
  const { t, lang } = useI18n();
  return (
    <>
      <PageHero eyebrow={eyebrow} title={title} lead={intro} />
      <div className="container-site grid gap-10 py-12 sm:py-16 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] lg:gap-14">
        <div className="rounded-[var(--radius-panel)] border border-border bg-surface p-6 shadow-[var(--shadow-card)] sm:p-8">{children}</div>
        <aside className="space-y-6" aria-label={t("Contact details", "بيانات التواصل")}>
          <div className="rounded-[var(--radius-panel)] border border-border bg-surface-subtle p-6 sm:p-8">
            <h2 className="font-display text-[22px] font-semibold">{t("Get in touch", "تواصل معنا")}</h2>
            <dl className="mt-5 space-y-5">
              {COMPANY.contact.map((c) => {
                const Icon = ICONS[c.key] ?? Info;
                return (
                  <div key={c.key} className="flex gap-3">
                    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-subtle text-brand"><Icon className="size-4" aria-hidden /></span>
                    <div>
                      <dt className="text-caption font-semibold uppercase tracking-[0.12em] text-fg-muted">{pick(c.label, lang)}</dt>
                      <dd className="mt-1 text-body leading-6 text-fg">{pick(c.value, lang)}</dd>
                    </div>
                  </div>
                );
              })}
            </dl>
            <p className="mt-6 flex gap-2 border-t border-border pt-4 text-caption text-fg-muted">
              <Info className="mt-px size-3.5 shrink-0" aria-hidden />
              {t("Prototype: these details are placeholders until confirmed by SmartEstate.", "نموذج تجريبي: هذه البيانات مؤقتة إلى أن تؤكدها SmartEstate.")}
            </p>
          </div>
          <div className="rounded-[var(--radius-panel)] border border-border p-6 sm:p-8">
            <h2 className="text-lead font-semibold">{t("Prefer to browse first?", "تفضّل التصفّح أولاً؟")}</h2>
            <p className="mt-1 text-body text-fg-secondary">{t("See available units and payment plans, or ask our assistant.", "اطّلع على الوحدات المتاحة وخطط الدفع، أو اسأل مساعدنا.")}</p>
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-body font-medium">
              <Link to="/projects" className="text-brand hover:underline">{t("Browse projects", "تصفّح المشاريع")}</Link>
              <Link to="/assistant" className="text-brand hover:underline">{t("Ask our Assistant", "اسأل مساعدنا")}</Link>
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}

export function ContactPage() {
  const { t } = useI18n();
  return (
    <Shell eyebrow={t("Contact", "تواصل معنا")} title={t("Contact us", "تواصل معنا")}
      intro={t("Tell us what you're looking for and we'll get back to you.", "أخبرنا بما تبحث عنه وسنعود إليك.")}>
      <InquiryForm kind="contact" />
    </Shell>
  );
}

export function ViewingPage() {
  const [params] = useSearchParams();
  const { t } = useI18n();
  return (
    <Shell eyebrow={t("Viewings", "الزيارات")} title={t("Request a viewing", "اطلب زيارة")}
      intro={t("Choose a project and a date — an advisor will confirm the time with you.", "اختر مشروعاً وموعداً — وسيؤكد أحد المستشارين الوقت معك.")}>
      <InquiryForm kind="viewing" projectCode={params.get("project") ?? ""} unitCode={params.get("unit") ?? ""} />
    </Shell>
  );
}
