import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import * as React from "react";
import { DemoDataNote, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Composer, SuggestedPrompts, Transcript } from "./chat";
import { useChatStream } from "./model";

const PROMPTS = {
  en: ["Show me 2-bedroom apartments under SAR 1,000,000", "What payment plans do you offer?", "Tell me about the project and its amenities"],
  ar: ["اعرض لي شققاً بغرفتي نوم بأقل من 1,000,000 ريال", "ما خطط الدفع المتاحة لديكم؟", "أخبرني عن المشروع ومرافقه"],
};

/** Public buyer chat (no sign-in), moved here from the dashboard in Phase 7A. Same backend endpoints and rules:
 *  public tools only, and contact details reach sales only with the visitor's explicit consent. */
export default function AssistantPage() {
  const { t, lang } = useI18n();
  const status = useQuery({
    queryKey: ["assistant", "status"],
    queryFn: () => api.get<{ available: boolean; message: string }>("/assistant/status"),
    staleTime: 60_000,
  });
  const chat = useChatStream("/assistant/messages");
  const [consent, setConsent] = React.useState(false);
  const available = status.data?.available ?? false;
  const send = (text: string) => void chat.send(text, { contact_consent: consent });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-10">
      <div>
        <h1 className="font-display text-h1 font-semibold tracking-[-0.015em]">{t("Ask our property assistant", "اسأل مساعدنا العقاري")}</h1>
        <p className="mt-1 text-lead text-fg-secondary">{t("Available units, prices and payment plans — answered from our live listings.", "الوحدات المتاحة والأسعار وخطط الدفع — إجابات من عروضنا الحالية.")}</p>
        <DemoDataNote className="mt-3" />
      </div>

      <section className="flex min-h-[420px] flex-col rounded-[var(--radius-panel)] border border-border bg-surface" aria-label={t("Property assistant chat", "محادثة المساعد العقاري")}>
        <div className="flex-1 p-4 sm:p-6">
          {status.isPending ? <Skeleton className="h-4 w-1/2" /> : !available ? (
            <p role="status" className="text-small text-fg-muted">{t("The assistant is not available right now. Please try again later, or use the contact form.", "المساعد غير متاح حالياً. يُرجى المحاولة لاحقاً أو استخدام نموذج التواصل.")}</p>
          ) : (
            <Transcript messages={chat.messages} empty={
              <div className="py-6">
                <p className="mb-3 text-small text-fg-muted">{t("Try one of these:", "جرّب أحد هذه الأسئلة:")}</p>
                <SuggestedPrompts prompts={PROMPTS[lang]} onPick={send} disabled={chat.busy} />
              </div>
            } />
          )}
        </div>
        <div className="space-y-2 border-t border-border-subtle p-3">
          <label className="flex items-start gap-2 text-small text-fg-secondary">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} disabled={!available}
              className="mt-0.5 size-4 accent-[var(--brand)]" />
            <span>
              <ShieldCheck className="me-1 inline size-3.5 align-[-2px] text-fg-muted" aria-hidden />
              {t("I agree that SmartEstate may store the name and contact details I share here and contact me about properties.", "أوافق على أن تحتفظ SmartEstate بالاسم وبيانات التواصل التي أشاركها هنا وتتواصل معي بخصوص العقارات.")}
            </span>
          </label>
          <Composer onSend={send} busy={chat.busy} disabled={!available} maxLength={1000}
            placeholder={t("Ask about units, prices or payment plans…", "اسأل عن الوحدات أو الأسعار أو خطط الدفع…")}
            footer={t("Answers are AI-generated from our listings. Don't share ID numbers or payment details.", "الإجابات مُنشأة بالذكاء الاصطناعي من عروضنا. لا تشارك أرقام الهوية أو بيانات الدفع.")} />
        </div>
      </section>
    </div>
  );
}
