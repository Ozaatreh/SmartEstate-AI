import { formatDate } from "@/lib/format";
import type { Campaign, Channel, ContentStatus } from "./api";

export function dateRange(c: Pick<Campaign, "start_date" | "end_date">): string {
  if (!c.start_date && !c.end_date) return "No dates set";
  return `${c.start_date ? formatDate(c.start_date) : "…"} – ${c.end_date ? formatDate(c.end_date) : "…"}`;
}

/** Mirrors CHANNEL_RULES in apps/api/app/modules/marketing/schemas.py (the API enforces them; this is for live feedback). */
export const CHANNELS: Record<Channel, { label: string; maxTotal: number; hashtags: boolean; headlineRequired: boolean; headlineLabel: string }> = {
  instagram: { label: "Instagram", maxTotal: 2200, hashtags: true, headlineRequired: false, headlineLabel: "Headline (optional)" },
  x: { label: "X", maxTotal: 280, hashtags: true, headlineRequired: false, headlineLabel: "Headline (optional)" },
  linkedin: { label: "LinkedIn", maxTotal: 3000, hashtags: true, headlineRequired: false, headlineLabel: "Headline (optional)" },
  email: { label: "Email", maxTotal: 5000, hashtags: false, headlineRequired: true, headlineLabel: "Subject line" },
  website: { label: "Website", maxTotal: 5000, hashtags: false, headlineRequired: true, headlineLabel: "Page title" },
  whatsapp: { label: "WhatsApp", maxTotal: 1000, hashtags: false, headlineRequired: false, headlineLabel: "Headline (optional)" },
};
export const CHANNEL_KEYS = Object.keys(CHANNELS) as Channel[];

export const CONTENT_STATUS_LABEL: Record<ContentStatus, string> = {
  draft: "Draft", pending_approval: "In review", approved: "Approved", rejected: "Changes requested", archived: "Archived",
};

/** Same formula as the API: headline, body, CTA and hashtags joined by newlines. */
export function totalLength(headline: string | null, body: string, cta: string | null, hashtags: string[]): number {
  return [headline, body, cta, hashtags.join(" ")].filter(Boolean).join("\n").length;
}

export function parseHashtags(raw: string): string[] {
  const out: string[] = [];
  for (const part of raw.split(/[\s,]+/)) {
    const t = part.trim();
    if (!t) continue;
    const tag = t.startsWith("#") ? t : `#${t}`;
    if (!out.some((x) => x.toLowerCase() === tag.toLowerCase())) out.push(tag);
  }
  return out;
}

export const HASHTAG_RE = /^#?[\p{L}\p{N}_]{1,50}$/u;

export function contentProblems(channel: Channel, headline: string, body: string, cta: string, hashtags: string[]): Record<string, string> {
  const rules = CHANNELS[channel];
  const e: Record<string, string> = {};
  if (!body.trim()) e.body = "Write the main text.";
  if (rules.headlineRequired && !headline.trim()) e.headline = `${rules.label} content needs a ${rules.headlineLabel.toLowerCase()}.`;
  if (hashtags.length && !rules.hashtags) e.hashtags = `${rules.label} content doesn't use hashtags.`;
  if (hashtags.some((t) => !HASHTAG_RE.test(t))) e.hashtags = "Hashtags use letters, digits and _ only.";
  const n = totalLength(headline || null, body, cta || null, hashtags);
  if (n > rules.maxTotal) e.body = `${rules.label} allows ${rules.maxTotal} characters; this is ${n}.`;
  return e;
}

export const isRtl = (language: string) => language === "ar";
