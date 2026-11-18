import { Info, Loader2, Sparkles } from "lucide-react";
import * as React from "react";
import { useI18n } from "@/lib/i18n";
import { statusLabel, toneFor, type Tone } from "@/lib/status";
import { cn } from "@/lib/utils";

// Small, dependency-free UI kit for the public site. Same design tokens as the dashboard (styles/tokens.css).

const BUTTON = {
  primary: "bg-primary text-primary-foreground hover:bg-primary-hover",
  brand: "bg-brand text-brand-foreground hover:bg-brand-hover",
  secondary: "border border-border-strong bg-transparent text-fg hover:border-fg/40 hover:bg-surface",
  ghost: "text-fg-secondary hover:bg-surface-sunken hover:text-fg",
  /** Light outline for dark bands and images. */
  onDark: "border border-white/35 bg-white/5 text-white backdrop-blur-sm hover:border-white/60 hover:bg-white/10",
} as const;
const SIZE = { sm: "h-8 px-3 text-small", md: "h-10 px-4 text-body", lg: "h-12 px-6 text-[15px]" } as const;

export function buttonClass(variant: keyof typeof BUTTON = "secondary", size: keyof typeof SIZE = "md", className?: string) {
  return cn(
    "press inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full font-medium tracking-[0.01em] " +
      "transition-[background-color,border-color,color,box-shadow,transform] duration-300 ease-[var(--ease-out-soft)] hover:shadow-[0_6px_18px_-8px_rgb(0_0_0/0.35)] " +
      "disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
    BUTTON[variant], SIZE[size], className,
  );
}

export function Button({ variant, size, loading, className, children, disabled, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof BUTTON; size?: keyof typeof SIZE; loading?: boolean;
}) {
  return (
    <button className={buttonClass(variant, size, className)} disabled={disabled || loading} aria-busy={loading || undefined} {...props}>
      {loading && <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden />}
      {children}
    </button>
  );
}

export const controlClass =
  "w-full rounded-[var(--radius-control)] border border-border-strong bg-canvas px-3 text-body text-fg placeholder:text-fg-muted " +
  "transition-[border-color,box-shadow,background-color] duration-300 ease-[var(--ease-out-soft)] hover:border-fg-subtle focus-visible:border-brand focus-visible:shadow-[0_0_0_4px_var(--brand-subtle)] " +
  "disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-fg-muted aria-[invalid=true]:border-danger";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn(controlClass, "h-10", className)} {...props} />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, rows = 4, ...props }, ref) => <textarea ref={ref} rows={rows} className={cn(controlClass, "py-2", className)} {...props} />,
);
Textarea.displayName = "Textarea";

export function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(controlClass, "h-10", className)} {...props}>{children}</select>;
}

export function Field({ label, htmlFor, error, hint, required, children }: {
  label: string; htmlFor: string; error?: string; hint?: string; required?: boolean; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-small font-medium text-fg">
        {label}{required && <span className="text-danger" aria-hidden> *</span>}
      </label>
      {children}
      {error ? <p id={`${htmlFor}-error`} className="text-caption text-danger">{error}</p>
        : hint ? <p className="text-caption text-fg-muted">{hint}</p> : null}
    </div>
  );
}

const TONE: Record<Tone, string> = {
  success: "bg-success-subtle text-success", warning: "bg-warning-subtle text-warning", danger: "bg-danger-subtle text-danger",
  info: "bg-info-subtle text-info", neutral: "bg-neutral-subtle text-neutral", brand: "bg-brand-subtle text-brand", ai: "bg-ai-subtle text-ai",
};

export function Badge({ tone = "neutral", className, children }: { tone?: Tone; className?: string; children: React.ReactNode }) {
  return <span className={cn("inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-full px-2 text-caption font-medium", TONE[tone], className)}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const { lang } = useI18n();
  return <Badge tone={toneFor(status)}>{statusLabel(status, lang)}</Badge>;
}

export function AiBadge({ label }: { label?: string }) {
  const { t } = useI18n();
  return <Badge tone="ai"><Sparkles className="size-3" aria-hidden />{label ?? t("AI-generated", "مُنشأ بالذكاء الاصطناعي")}</Badge>;
}

export function DemoDataNote({ className }: { className?: string }) {
  const { t } = useI18n();
  return (
    <p role="note" className={cn("inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-caption text-fg-muted", className)}>
      <Info className="size-3.5" aria-hidden /> {t("Illustrative / Fictional Demo Data", "بيانات توضيحية / تجريبية وهمية")}
    </p>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("skeleton-shimmer rounded-[var(--radius-control)]", className)} />;
}

export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-[var(--radius-panel)] border border-danger/40 bg-danger/5 px-4 py-3 text-body">
      <span className="flex-1">{message}</span>
      {onRetry && <Button size="sm" onClick={onRetry}>{t("Try again", "حاول مجدداً")}</Button>}
    </div>
  );
}

/** Section heading block used across the public pages: eyebrow, serif title, optional lead. */
export function SectionHeading({ eyebrow, title, lead, id, align = "start", className }: {
  eyebrow?: string; title: React.ReactNode; lead?: React.ReactNode; id?: string; align?: "start" | "center"; className?: string;
}) {
  return (
    <div className={cn("max-w-2xl", align === "center" && "mx-auto text-center", className)}>
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h2 id={id} className="mt-3 font-display text-[30px] font-semibold leading-[1.15] tracking-[-0.02em] text-fg sm:text-[38px]">{title}</h2>
      {lead && <p className="mt-4 text-lead text-fg-secondary sm:text-[17px] sm:leading-7">{lead}</p>}
    </div>
  );
}

/** Page title block (top of inner pages). */
export function PageHero({ eyebrow, title, lead, children }: { eyebrow: string; title: React.ReactNode; lead?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <section className="border-b border-border bg-surface-subtle">
      <div className="container-site py-14 sm:py-20">
        <p className="eyebrow enter-fade">{eyebrow}</p>
        <h1 style={{ "--d": "80ms" } as React.CSSProperties} className="enter-up mt-3 max-w-3xl font-display text-[36px] font-semibold leading-[1.1] tracking-[-0.025em] sm:text-[52px]">{title}</h1>
        {lead && <p style={{ "--d": "200ms" } as React.CSSProperties} className="enter-up mt-5 max-w-2xl text-lead text-fg-secondary sm:text-[18px] sm:leading-8">{lead}</p>}
        {children && <div style={{ "--d": "320ms" } as React.CSSProperties} className="enter-fade">{children}</div>}
      </div>
    </section>
  );
}
