import { useQuery } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { Button, Field, Input, Select, Textarea } from "@/components/ui";
import { api, ApiError, type PublicProject } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { inDays, today, validate, type Errors, type InquiryKind, type Values } from "./validation";

export function InquiryForm({ kind, projectCode = "", unitCode = "" }: { kind: InquiryKind; projectCode?: string; unitCode?: string }) {
  const { t, lang } = useI18n();
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api.get<PublicProject[]>("/projects"), enabled: kind === "viewing" });
  // A fresh token every time the form is shown: submissions that come back too fast are treated as bots.
  const token = useQuery({ queryKey: ["inquiry-token", kind], queryFn: () => api.get<{ token: string }>("/inquiries/form-token"), staleTime: 0, gcTime: 0 });
  const [v, setV] = React.useState<Values>({
    full_name: "", email: "", phone: "", message: "", project_code: projectCode.toUpperCase(), unit_code: unitCode.toUpperCase(),
    preferred_date: "", preferred_language: lang, consent: false, website: "",
  });
  const [errors, setErrors] = React.useState<Errors>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [sending, setSending] = React.useState(false);
  const [done, setDone] = React.useState<string | null>(null);
  const set = <K extends keyof Values>(k: K) => (value: Values[K]) => { setV((x) => ({ ...x, [k]: value })); setErrors((e) => ({ ...e, [k]: undefined, contact: undefined })); };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs = validate(kind, v, lang);
    setErrors(errs);
    setFormError(null);
    if (Object.values(errs).some(Boolean)) return;
    setSending(true);
    try {
      const res = await api.post<{ message: string }>("/inquiries", {
        kind, full_name: v.full_name.trim(), email: v.email.trim() || null, phone: v.phone.trim() || null,
        message: v.message.trim() || null, project_code: v.project_code || null, unit_code: v.unit_code || null,
        preferred_date: kind === "viewing" ? v.preferred_date : null, preferred_language: v.preferred_language,
        consent: v.consent, website: v.website, form_token: token.data?.token ?? "",
      });
      setDone(res.message);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setErrors(err.fieldErrors);
        setFormError(err.formErrors[0] ?? err.message);
        if (err.fieldErrors.form_token) void token.refetch();
      } else {
        setFormError(err instanceof ApiError ? err.message : t("Something went wrong. Please try again.", "حدث خطأ ما. يُرجى المحاولة مجدداً."));
      }
    } finally {
      setSending(false);
    }
  };

  if (done) {
    return (
      <div role="status" className="rounded-[var(--radius-panel)] border border-success/40 bg-success/5 p-6">
        <CheckCircle2 className="mb-2 size-6 text-success" aria-hidden />
        <p className="text-lead font-semibold">{t("Request received", "تم استلام طلبك")}</p>
        <p className="mt-1 text-body text-fg-secondary">{done}</p>
        <Link to="/projects" className="mt-4 inline-block text-body text-brand hover:underline">{t("Keep browsing projects →", "← تابع تصفّح المشاريع")}</Link>
      </div>
    );
  }

  const err = (k: string) => errors[k];
  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-label={kind === "viewing" ? t("Request a viewing", "اطلب زيارة") : t("Contact us", "تواصل معنا")}>
      {formError && <p role="alert" className="rounded-[var(--radius-control)] border border-danger/40 bg-danger/5 px-3 py-2 text-small">{formError}</p>}
      <Field label={t("Full name", "الاسم الكامل")} htmlFor="q-name" required error={err("full_name")}>
        <Input id="q-name" autoComplete="name" maxLength={150} value={v.full_name} onChange={(e) => set("full_name")(e.target.value)} aria-invalid={!!err("full_name")} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("Phone", "الهاتف")} htmlFor="q-phone" error={err("phone")}>
          <Input id="q-phone" dir="ltr" type="tel" autoComplete="tel" maxLength={40} value={v.phone} onChange={(e) => set("phone")(e.target.value)} aria-invalid={!!err("phone")} />
        </Field>
        <Field label={t("E-mail", "البريد الإلكتروني")} htmlFor="q-email" error={err("email")}>
          <Input id="q-email" dir="ltr" type="email" autoComplete="email" maxLength={254} value={v.email} onChange={(e) => set("email")(e.target.value)} aria-invalid={!!err("email")} />
        </Field>
      </div>
      {err("contact") && <p className="-mt-2 text-caption text-danger">{err("contact")}</p>}
      {kind === "viewing" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("Project", "المشروع")} htmlFor="q-project" required error={err("project_code")}>
            <Select id="q-project" value={v.project_code} onChange={(e) => { set("project_code")(e.target.value); set("unit_code")(""); }} aria-invalid={!!err("project_code")}>
              <option value="">{t("Choose a project…", "اختر مشروعاً…")}</option>
              {(projects.data ?? []).map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
              {v.project_code && !projects.data?.some((p) => p.code === v.project_code) && <option value={v.project_code}>{v.project_code}</option>}
            </Select>
          </Field>
          <Field label={t("Preferred date", "الموعد المفضّل")} htmlFor="q-date" required error={err("preferred_date")}>
            <Input id="q-date" type="date" min={today()} max={inDays(90)} value={v.preferred_date} onChange={(e) => set("preferred_date")(e.target.value)} aria-invalid={!!err("preferred_date")} />
          </Field>
          {v.unit_code && <p className="text-small text-fg-secondary sm:col-span-2">{t("Unit:", "الوحدة:")} <span className="font-medium tabular">{v.unit_code}</span></p>}
        </div>
      )}
      <Field label={kind === "viewing" ? t("Anything we should know? (optional)", "هل هناك ما يجب أن نعرفه؟ (اختياري)") : t("Message", "الرسالة")} htmlFor="q-message" required={kind === "contact"} error={err("message")}>
        <Textarea id="q-message" maxLength={1000} value={v.message} onChange={(e) => set("message")(e.target.value)} aria-invalid={!!err("message")} />
      </Field>
      <Field label={t("Preferred language", "اللغة المفضّلة")} htmlFor="q-lang">
        <Select id="q-lang" value={v.preferred_language} onChange={(e) => set("preferred_language")(e.target.value as "en" | "ar")}>
          <option value="en">English</option>
          <option value="ar">العربية (Arabic)</option>
        </Select>
      </Field>
      {/* Honeypot: hidden from people and assistive technology; bots that fill it are ignored by the server. */}
      <div aria-hidden="true" className="pointer-events-none absolute h-px w-px overflow-hidden whitespace-nowrap opacity-0 [clip-path:inset(50%)]">
        <label htmlFor="q-website">{t("Website", "الموقع الإلكتروني")}</label>
        <input id="q-website" name="website" tabIndex={-1} autoComplete="off" value={v.website} onChange={(e) => set("website")(e.target.value)} />
      </div>
      <div>
        <label className="flex items-start gap-2 text-small text-fg-secondary">
          <input type="checkbox" checked={v.consent} onChange={(e) => set("consent")(e.target.checked)} className="mt-0.5 size-4 accent-[var(--brand)]" aria-invalid={!!err("consent")} />
          <span>{t("I agree that SmartEstate may store my details and contact me about this request.", "أوافق على أن تحتفظ SmartEstate ببياناتي وتتواصل معي بخصوص هذا الطلب.")}</span>
        </label>
        {err("consent") && <p className="mt-1 text-caption text-danger">{err("consent")}</p>}
      </div>
      <Button type="submit" variant="brand" size="lg" loading={sending} disabled={token.isPending}>
        {kind === "viewing" ? t("Request a viewing", "اطلب زيارة") : t("Send message", "إرسال الرسالة")}
      </Button>
    </form>
  );
}
