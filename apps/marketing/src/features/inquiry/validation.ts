export type InquiryKind = "contact" | "viewing";
export type Errors = Partial<Record<string, string>>;

export interface Values {
  full_name: string; email: string; phone: string; message: string; project_code: string; unit_code: string;
  preferred_date: string; preferred_language: "en" | "ar"; consent: boolean; website: string;
}

export const today = () => new Date().toISOString().slice(0, 10);
export const inDays = (n: number) => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10);

/** Client-side checks for quick feedback only; the server validates everything again and decides. */
export function validate(kind: InquiryKind, v: Values, lang: "en" | "ar" = "en"): Errors {
  const t = (en: string, ar: string) => (lang === "ar" ? ar : en);
  const e: Errors = {};
  if (v.full_name.trim().length < 2) e.full_name = t("Enter your name.", "أدخل اسمك.");
  if (!v.email.trim() && !v.phone.trim()) e.contact = t("Give us a phone number or an e-mail address.", "أدخل رقم هاتف أو بريداً إلكترونياً.");
  if (v.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.email.trim())) e.email = t("Enter a valid e-mail address.", "أدخل بريداً إلكترونياً صحيحاً.");
  if (v.phone.trim() && (!/^[+0-9 ()\-.]{7,40}$/.test(v.phone.trim()) || v.phone.replace(/\D/g, "").length < 7)) e.phone = t("Enter a valid phone number.", "أدخل رقم هاتف صحيحاً.");
  if (kind === "contact" && !v.message.trim()) e.message = t("Write a short message.", "اكتب رسالة قصيرة.");
  if (kind === "viewing") {
    if (!v.project_code) e.project_code = t("Choose a project.", "اختر مشروعاً.");
    if (!v.preferred_date) e.preferred_date = t("Choose a date.", "اختر موعداً.");
    else if (v.preferred_date < today() || v.preferred_date > inDays(90)) e.preferred_date = t("Choose a date within the next 90 days.", "اختر موعداً خلال الأيام التسعين القادمة.");
  }
  if (!v.consent) e.consent = t("Please agree so we can contact you.", "يُرجى الموافقة حتى نتمكن من التواصل معك.");
  return e;
}

