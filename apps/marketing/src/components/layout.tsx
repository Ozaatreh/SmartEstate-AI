import { Languages, Menu, MoonStar, Sun, X } from "lucide-react";
import * as React from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Wordmark } from "@/components/brand";
import { buttonClass, DemoDataNote } from "@/components/ui";
import { COMPANY, pick, type Text } from "@/content/company";
import { useI18n } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

interface NavItem { to: string; label: Text; end?: boolean }

const NAV: NavItem[] = [
  { to: "/", label: { en: "Home", ar: "الرئيسية" }, end: true },
  { to: "/projects", label: { en: "Projects", ar: "المشاريع" } },
  { to: "/about", label: { en: "About Us", ar: "من نحن" } },
  { to: "/contact", label: { en: "Contact", ar: "تواصل معنا" } },
];
const ASSISTANT: NavItem = { to: "/assistant", label: { en: "Ask our Assistant", ar: "اسأل مساعدنا" } };
const VIEWING: Text = { en: "Request a Viewing", ar: "اطلب زيارة" };
const DASHBOARD_URL = import.meta.env.VITE_DASHBOARD_URL ?? "http://localhost:5174";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme();
  const { t } = useI18n();
  const dark = theme === "dark";
  return (
    <button type="button" onClick={toggle} aria-pressed={dark}
      aria-label={dark ? t("Switch to light theme", "التبديل إلى الوضع الفاتح") : t("Switch to dark theme", "التبديل إلى الوضع الداكن")}
      title={dark ? t("Light theme", "الوضع الفاتح") : t("Dark theme", "الوضع الداكن")}
      className={cn("press grid size-10 place-items-center rounded-full text-fg-secondary transition-colors hover:bg-surface-sunken hover:text-fg", className)}>
      <span key={theme} className="grid duration-500 animate-in fade-in-0 spin-in-[60deg] zoom-in-75 motion-reduce:animate-none">
        {dark ? <Sun className="size-[18px]" aria-hidden /> : <MoonStar className="size-[18px]" aria-hidden />}
      </span>
    </button>
  );
}

/** Switches the whole site between English and Arabic; the button names the other language in that language. */
export function LanguageSwitch({ className }: { className?: string }) {
  const { lang, setLang } = useI18n();
  const other = lang === "ar" ? "en" : "ar";
  return (
    <button type="button" onClick={() => setLang(other)}
      aria-label={other === "ar" ? "التبديل إلى العربية" : "Switch to English"} title={other === "ar" ? "العربية" : "English"}
      className={cn("inline-flex h-10 items-center gap-1.5 rounded-full px-3 text-small font-medium text-fg-secondary transition-colors hover:bg-surface-sunken hover:text-fg", className)}>
      <Languages className="size-4" aria-hidden />
      <span lang={other} className={other === "ar" ? "font-[family-name:var(--font-arabic)]" : ""}>{other === "ar" ? "العربية" : "English"}</span>
    </button>
  );
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn("relative px-3 py-2 text-body transition-colors after:absolute after:inset-x-3 after:-bottom-px after:h-px after:bg-brand after:transition-transform after:duration-500 after:ease-[var(--ease-out-soft)]",
    isActive ? "text-fg after:scale-x-100" : "text-fg-secondary after:scale-x-0 hover:text-fg hover:after:scale-x-50");

export function SiteLayout() {
  const [open, setOpen] = React.useState(false);
  const { pathname } = useLocation();
  const { t, lang } = useI18n();
  const [scrolled, setScrolled] = React.useState(false);
  React.useEffect(() => { window.scrollTo?.(0, 0); }, [pathname]);
  // Transparent header at the top of the page, solid once the visitor scrolls.
  React.useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="flex min-h-dvh flex-col bg-canvas text-fg">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:start-4 focus:top-4 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        {t("Skip to content", "انتقل إلى المحتوى")}
      </a>
      <header data-scrolled={scrolled || open || undefined}
        className={cn("sticky top-0 z-30 border-b transition-[background-color,border-color,box-shadow] duration-500 ease-[var(--ease-out-soft)]",
          scrolled || open ? "border-border bg-canvas/90 shadow-[0_8px_24px_-18px_rgb(0_0_0/0.35)] backdrop-blur-md" : "border-transparent bg-transparent")}>
        <div className="container-site flex h-[68px] items-center justify-between gap-4">
          <Link to="/" aria-label={t("SmartEstate home", "الصفحة الرئيسية لـ SmartEstate")}><Wordmark /></Link>
          <nav aria-label={t("Main", "القائمة الرئيسية")} className="hidden items-center lg:flex">
            {NAV.map((n) => <NavLink key={n.to} to={n.to} end={n.end} className={navClass}>{pick(n.label, lang)}</NavLink>)}
            <span className="mx-2 h-5 w-px bg-border" aria-hidden />
            <NavLink to={ASSISTANT.to} className={({ isActive }) => cn("px-3 py-2 text-small transition-colors", isActive ? "text-fg" : "text-fg-muted hover:text-fg")}>
              {pick(ASSISTANT.label, lang)}
            </NavLink>
          </nav>
          <div className="flex items-center gap-1">
            <LanguageSwitch className="hidden sm:inline-flex" />
            <ThemeToggle />
            <Link to="/request-viewing" className={buttonClass("brand", "md", "ms-1 hidden sm:inline-flex")}>{pick(VIEWING, lang)}</Link>
            <button type="button" className="grid size-10 place-items-center rounded-full text-fg hover:bg-surface-sunken lg:hidden" onClick={() => setOpen((o) => !o)}
              aria-expanded={open} aria-controls="mobile-nav" aria-label={open ? t("Close menu", "إغلاق القائمة") : t("Open menu", "فتح القائمة")}>
              {open ? <X className="size-5 duration-300 animate-in spin-in-90 fade-in-0 motion-reduce:animate-none" /> : <Menu className="size-5 duration-300 animate-in fade-in-0" />}
            </button>
          </div>
        </div>
        {open && (
          <nav id="mobile-nav" aria-label={t("Main", "القائمة الرئيسية")}
            className="border-t border-border bg-canvas duration-300 animate-in fade-in-0 slide-in-from-top-2 motion-reduce:animate-none lg:hidden">
            <div className="container-site py-3">
              {[...NAV, ASSISTANT].map((n, i) => (
                <NavLink key={n.to} to={n.to} end={n.end} onClick={() => setOpen(false)} style={{ "--d": `${60 + i * 45}ms` } as React.CSSProperties}
                  className={({ isActive }) => cn("enter-up block border-b border-border-subtle py-3 text-lead last:border-0", isActive ? "font-medium text-fg" : "text-fg-secondary")}>
                  {pick(n.label, lang)}
                </NavLink>
              ))}
              <LanguageSwitch className="mt-2 -ms-3 sm:hidden" />
              <Link to="/request-viewing" onClick={() => setOpen(false)} className={buttonClass("brand", "lg", "mt-3 w-full")}>{pick(VIEWING, lang)}</Link>
            </div>
          </nav>
        )}
      </header>

      {/* A gentle fade on each route change (keyed by path only, so #anchors and ?query changes don't replay it). */}
      <main id="main" className="flex-1"><div key={pathname} className="page-enter"><Outlet /></div></main>

      <footer className="border-t border-border bg-surface-subtle">
        <div className="container-site grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr]">
          <div className="space-y-4">
            <Wordmark />
            <p className="max-w-sm text-small leading-6 text-fg-secondary">{pick(COMPANY.summary, lang)}</p>
            <DemoDataNote />
          </div>
          <FooterColumn title={t("Explore", "استكشف")} links={[NAV[1]!, { to: "/request-viewing", label: VIEWING }, ASSISTANT]} />
          <FooterColumn title={t("Company", "الشركة")} links={[NAV[2]!, NAV[3]!]} />
          <div>
            <p className="mb-3 text-small font-semibold text-fg">{t("Visit", "زورونا")}</p>
            <ul className="space-y-2 text-small text-fg-secondary">
              {COMPANY.contact.slice(0, 2).map((c) => <li key={c.key}>{pick(c.value, lang)}</li>)}
              <li><a href={DASHBOARD_URL} className="hover:text-fg">{t("Staff sign-in", "دخول الموظفين")}</a></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-border-subtle">
          <p className="container-site py-5 text-caption text-fg-muted">
            © {new Date().getFullYear()} SmartEstate · {t("Prototype with fictional data", "نموذج أولي ببيانات وهمية")}
          </p>
        </div>
      </footer>
    </div>
  );
}

function FooterColumn({ title, links }: { title: string; links: NavItem[] }) {
  const { lang } = useI18n();
  return (
    <div>
      <p className="mb-3 text-small font-semibold text-fg">{title}</p>
      <ul className="space-y-2 text-small text-fg-secondary">
        {links.map((l) => <li key={l.to}><Link to={l.to} className="transition-colors hover:text-fg">{pick(l.label, lang)}</Link></li>)}
      </ul>
    </div>
  );
}
