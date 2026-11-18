import * as React from "react";

/**
 * Public website language: English or Arabic (right-to-left).
 *
 * index.html applies the language before the first paint (`?lang=` in the URL, else the saved choice, else English),
 * setting <html lang dir>. Text is written next to its use as `t("English", "العربية")`, so both versions stay together.
 * Content stored in the database (project names, descriptions, amenities) is shown as stored.
 */
export type Lang = "en" | "ar";
export const LANG_KEY = "smartestate-lang";

const active = { lang: "en" as Lang };
/** The active language, for non-React helpers (number and date formatting). */
export const activeLang = () => active.lang;
/** Set during render, so formatting in the same render already uses the new language. */
function setActiveLang(lang: Lang) { active.lang = lang; }

function initialLang(): Lang {
  if (typeof document === "undefined") return "en";
  return document.documentElement.lang === "ar" ? "ar" : "en";
}

export function applyLang(lang: Lang) {
  setActiveLang(lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}

interface I18n {
  lang: Lang;
  dir: "ltr" | "rtl";
  setLang: (lang: Lang) => void;
  /** Picks the text for the active language. */
  t: (en: string, ar: string) => string;
}

const Ctx = React.createContext<I18n>({ lang: "en", dir: "ltr", setLang: () => undefined, t: (en) => en });

export function I18nProvider({ children, initial }: { children: React.ReactNode; initial?: Lang }) {
  const [lang, setLangState] = React.useState<Lang>(() => initial ?? initialLang());
  setActiveLang(lang);

  React.useEffect(() => { applyLang(lang); }, [lang]);

  const setLang = React.useCallback((l: Lang) => {
    try { localStorage.setItem(LANG_KEY, l); } catch { /* private mode: lasts for this page only */ }
    // Keep a shared link's ?lang= in step with the choice.
    const url = new URL(window.location.href);
    if (url.searchParams.has("lang")) {
      url.searchParams.set("lang", l);
      window.history.replaceState(window.history.state, "", url);
    }
    setLangState(l);
  }, []);

  const value = React.useMemo<I18n>(() => ({
    lang, dir: lang === "ar" ? "rtl" : "ltr", setLang, t: (en, ar) => (lang === "ar" ? ar : en),
  }), [lang, setLang]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useI18n = () => React.useContext(Ctx);
