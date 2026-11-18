import { Link } from "react-router-dom";
import { buttonClass } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

const WHAT = { page: { en: "page", ar: "الصفحة" }, project: { en: "project", ar: "المشروع" }, unit: { en: "unit", ar: "الوحدة" } };

export default function NotFoundPage({ what = "page" }: { what?: "page" | "project" | "unit" }) {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-xl px-4 py-24 text-center">
      <p className="eyebrow">{t("Not found", "غير موجود")}</p>
      <h1 className="mt-2 font-display text-h1 font-semibold">{t(`We couldn't find that ${WHAT[what].en}`, `لم نتمكن من العثور على ${WHAT[what].ar}`)}</h1>
      <p className="mt-2 text-body text-fg-secondary">{t("It may no longer be listed. Browse our current projects instead.", "ربما لم تعد معروضة. تصفّح مشاريعنا الحالية بدلاً من ذلك.")}</p>
      <Link to="/projects" className={buttonClass("primary", "md", "mt-6")}>{t("Browse projects", "تصفّح المشاريع")}</Link>
    </div>
  );
}
