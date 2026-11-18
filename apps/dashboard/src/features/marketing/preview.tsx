import { Building2 } from "lucide-react";
import { LogoMark } from "@/components/system/brand";
import { cn } from "@/lib/utils";
import type { Channel, Language } from "./api";
import { CHANNELS, isRtl, totalLength } from "./logic";

export interface PreviewProps {
  channel: Channel; language: Language; headline: string; body: string; cta: string; hashtags: string[]; projectName: string;
}

/** How the content would read on its channel. A preview only: nothing is ever posted from SmartEstate. */
export function ContentPreview(p: PreviewProps) {
  const rtl = isRtl(p.language);
  const n = totalLength(p.headline || null, p.body, p.cta || null, p.hashtags);
  const limit = CHANNELS[p.channel].maxTotal;
  const text = (
    <div lang={p.language} dir={rtl ? "rtl" : "ltr"} className="space-y-2 text-body">
      {p.headline && p.channel !== "email" && p.channel !== "website" && <p className="font-semibold">{p.headline}</p>}
      <p className="whitespace-pre-line break-words">{p.body || <span className="text-fg-muted">Your text appears here…</span>}</p>
      {p.cta && p.channel !== "email" && p.channel !== "website" && <p className="font-medium">{p.cta}</p>}
      {p.hashtags.length > 0 && <p className="break-words text-brand">{p.hashtags.join(" ")}</p>}
    </div>
  );
  const account = (
    <div className="flex items-center gap-2">
      <LogoMark className="size-8" />
      <div className="leading-tight"><p className="text-small font-semibold">SmartEstate</p><p className="text-caption text-fg-muted">{p.projectName}</p></div>
    </div>
  );

  let frame: React.ReactNode;
  switch (p.channel) {
    case "instagram":
      frame = (
        <div className="overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface">
          <div className="p-3">{account}</div>
          <div className="grid aspect-square place-items-center bg-[linear-gradient(135deg,var(--brand-subtle),var(--surface-sunken))]" aria-hidden>
            <Building2 className="size-10 text-brand/60" />
          </div>
          <div className="p-3">{text}</div>
        </div>
      );
      break;
    case "email":
    case "website":
      frame = (
        <div className="overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface">
          <div className="border-b border-border-subtle bg-surface-subtle px-3 py-2 text-caption text-fg-muted">
            {p.channel === "email" ? <>From SmartEstate · <span className="font-medium text-fg">Subject:</span> <span lang={p.language} dir={rtl ? "rtl" : "ltr"}>{p.headline || "—"}</span></> : "smartestate.example / " + p.projectName}
          </div>
          <div className="space-y-3 p-4" lang={p.language} dir={rtl ? "rtl" : "ltr"}>
            {p.channel === "website" && <h3 className="font-display text-h3 font-semibold">{p.headline || "Page title"}</h3>}
            <p className="whitespace-pre-line break-words text-body">{p.body || <span className="text-fg-muted">Your text appears here…</span>}</p>
            {p.cta && <span className="inline-flex h-9 items-center rounded-[var(--radius-control)] bg-brand px-4 text-small font-medium text-on-accent">{p.cta}</span>}
          </div>
        </div>
      );
      break;
    case "whatsapp":
      frame = (
        <div className="rounded-[var(--radius-control)] bg-surface-sunken p-3">
          <div className={cn("max-w-[90%] rounded-[12px] bg-success-subtle p-3 shadow-sm", rtl ? "mr-auto" : "ml-auto")}>{text}</div>
        </div>
      );
      break;
    default:
      frame = <div className="space-y-3 rounded-[var(--radius-control)] border border-border bg-surface p-3">{account}{text}</div>;
  }

  return (
    <div className="space-y-2">
      {frame}
      <p className={cn("text-caption", n > limit ? "font-medium text-danger" : "text-fg-muted")}>
        {n.toLocaleString()} / {limit.toLocaleString()} characters · {CHANNELS[p.channel].label}
      </p>
    </div>
  );
}
