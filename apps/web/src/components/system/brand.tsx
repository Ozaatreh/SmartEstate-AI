import { cn } from "@/lib/utils";

/** SmartEstate mark: two stacked rooflines forming an abstract "S" (UI_UX_DESIGN.md § 2.4). */
export function LogoMark({ className, title = "SmartEstate AI" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} role="img" aria-label={title}>
      <rect width="32" height="32" rx="7" fill="var(--brand)" />
      <path d="M8 14.5 16 8l8 6.5" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M8 17.5h10.5a3.5 3.5 0 0 1 0 7H8" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" opacity=".92" />
    </svg>
  );
}

export function Wordmark({ collapsed = false, className }: { collapsed?: boolean; className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      {!collapsed && (
        <span className="text-[15px] font-semibold tracking-[-0.01em] text-fg">
          SmartEstate <span className="font-medium text-fg-muted">AI</span>
        </span>
      )}
    </span>
  );
}
