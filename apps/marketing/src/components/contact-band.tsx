import { Link } from "react-router-dom";
import { Reveal } from "@/components/motion";
import { buttonClass } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

/** Closing call to action (home and About pages). */
export function ContactBand() {
  const { t } = useI18n();
  return (
    <section className="px-4 pb-16 sm:px-6 sm:pb-24 lg:px-8" aria-labelledby="cta-heading">
      <Reveal className="relative mx-auto max-w-[76rem] overflow-hidden rounded-[28px] bg-surface-inverse px-6 py-14 text-white sm:px-14 sm:py-20">
        <img src="/images/villa-front.webp" alt="" aria-hidden className="absolute inset-0 size-full object-cover opacity-25" loading="lazy" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#1b2129] via-[#1b2129]/85 to-transparent rtl:bg-gradient-to-l" aria-hidden />
        <div className="relative max-w-xl">
          <p className="text-eyebrow font-semibold uppercase tracking-[0.18em] text-[#e0a47c]">{t("Visit us", "زورونا")}</p>
          <h2 id="cta-heading" className="mt-3 font-display text-[30px] font-semibold leading-[1.15] tracking-[-0.02em] sm:text-[40px]">{t("See your next home in person.", "شاهد منزلك القادم على أرض الواقع.")}</h2>
          <p className="mt-4 text-lead text-white/75">{t("Choose a project and a date — an advisor will confirm the time with you. Questions first? Send us a message.", "اختر مشروعاً وموعداً — وسيؤكد أحد المستشارين الوقت معك. لديك أسئلة أولاً؟ أرسل لنا رسالة.")}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/request-viewing" className={buttonClass("brand", "lg")}>{t("Request a Viewing", "اطلب زيارة")}</Link>
            <Link to="/contact" className={buttonClass("onDark", "lg")}>{t("Contact us", "تواصل معنا")}</Link>
          </div>
        </div>
      </Reveal>
    </section>
  );
}
