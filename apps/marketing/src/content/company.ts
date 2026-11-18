/**
 * Company information shown on the public website — the one place to edit it, in English and Arabic.
 *
 * NOTHING here is verified company data. SmartEstate AI is a prototype: there is no confirmed founding date, team,
 * licence, address, phone, e-mail or opening hours in the system (the brochure generator also reports "Contact details
 * aren't configured"). Every entry below is a PLACEHOLDER and must be replaced or approved before launch.
 * Do not add achievements, customer numbers, certifications or completed projects without evidence.
 */
import type { Lang } from "@/lib/i18n";

export interface Text { en: string; ar: string }
export const pick = (text: Text, lang: Lang) => text[lang];

export interface CompanyFact {
  key: "location" | "hours" | "response";
  label: Text;
  value: Text;
  /** True until the business confirms the value. */
  placeholder: boolean;
}

export const COMPANY = {
  name: "SmartEstate",
  /** PLACEHOLDER — positioning statement (existing site copy, not yet approved). */
  summary: {
    en: "SmartEstate develops residential communities in Saudi Arabia, with flexible payment plans and a sales team that follows up on every inquiry.",
    ar: "تطوّر SmartEstate مجتمعات سكنية في المملكة العربية السعودية، مع خطط دفع مرنة وفريق مبيعات يتابع كل استفسار.",
  },
  contact: [
    { key: "location", label: { en: "Sales centre", ar: "مركز المبيعات" }, value: { en: "Riyadh, Saudi Arabia", ar: "الرياض، المملكة العربية السعودية" }, placeholder: true },
    { key: "hours", label: { en: "Opening hours", ar: "ساعات العمل" }, value: { en: "Sunday–Thursday, 9:00–18:00", ar: "الأحد – الخميس، 9:00 – 18:00" }, placeholder: true },
    {
      key: "response", label: { en: "Response", ar: "الرد" },
      value: { en: "An advisor follows up on every request, usually within one working day.", ar: "يتابع أحد مستشارينا كل طلب، عادةً خلال يوم عمل واحد." },
      placeholder: true,
    },
  ] satisfies CompanyFact[],
};

/** About-page copy. PLACEHOLDER text describing the approach; it makes no factual claims about history or results. */
export const ABOUT = {
  intro: {
    en: "SmartEstate brings residential projects, live availability and payment plans together in one place, so choosing a home starts with clear, current information.",
    ar: "تجمع SmartEstate المشاريع السكنية والوحدات المتاحة وخطط الدفع في مكان واحد، ليبدأ اختيار منزلك بمعلومات واضحة ومحدّثة.",
  },
  mission: {
    en: "To make finding and buying a home straightforward: accurate listings, transparent payment options and a team that answers every question.",
    ar: "أن نجعل البحث عن منزل وشراءه أمراً سهلاً: عروض دقيقة، وخيارات دفع واضحة، وفريق يجيب عن كل سؤال.",
  },
  vision: {
    en: "Residential communities that are well designed, well connected and easy to understand before you ever visit.",
    ar: "مجتمعات سكنية مدروسة التصميم، جيدة الاتصال، وسهلة الفهم حتى قبل زيارتها.",
  },
  approach: [
    {
      title: { en: "Information you can rely on", ar: "معلومات يمكنك الاعتماد عليها" },
      text: { en: "Prices, availability and payment plans on this website come straight from our sales system, not from brochures that go out of date.", ar: "الأسعار والوحدات المتاحة وخطط الدفع على هذا الموقع تأتي مباشرة من نظام المبيعات، لا من كتيّبات قد تصبح قديمة." },
    },
    {
      title: { en: "Clear choices", ar: "خيارات واضحة" },
      text: { en: "Each project shows what is actually available, with unit sizes and the payment plans you can choose from.", ar: "يعرض كل مشروع ما هو متاح فعلاً، مع مساحات الوحدات وخطط الدفع التي يمكنك الاختيار منها." },
    },
    {
      title: { en: "People who follow up", ar: "فريق يتابع معك" },
      text: { en: "Every inquiry and viewing request reaches our sales team, who contact you about your request.", ar: "يصل كل استفسار وطلب زيارة إلى فريق المبيعات، الذي يتواصل معك بخصوص طلبك." },
    },
  ],
  services: [
    { title: { en: "Project discovery", ar: "اكتشاف المشاريع" }, text: { en: "Browse published projects, their amenities and the units available today.", ar: "تصفّح المشاريع المنشورة ومرافقها والوحدات المتاحة اليوم." } },
    { title: { en: "Payment plans", ar: "خطط الدفع" }, text: { en: "Compare the payment plans offered for each project before you speak to us.", ar: "قارن خطط الدفع المتاحة لكل مشروع قبل أن تتحدث إلينا." } },
    { title: { en: "Viewings", ar: "الزيارات" }, text: { en: "Request a viewing online and an advisor confirms the time with you.", ar: "اطلب زيارة عبر الإنترنت وسيؤكد أحد المستشارين الموعد معك." } },
    { title: { en: "Property assistant", ar: "المساعد العقاري" }, text: { en: "Ask our assistant about listed units, sizes and prices — it answers from the live listings.", ar: "اسأل مساعدنا عن الوحدات المعروضة ومساحاتها وأسعارها — يجيب من العروض الحالية." } },
  ],
};
