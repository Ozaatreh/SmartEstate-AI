import { AlertTriangle, ArrowUp, Ban, Check, CircleAlert, Loader2, UserRoundCheck } from "lucide-react";
import * as React from "react";
import { AiBadge, StatusBadge } from "@/components/system/badges";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { formatMoney } from "@/lib/format";
import { humanize } from "@/lib/status";
import { cn } from "@/lib/utils";
import { columnLabel, type ChatMessage, type PublicUnit, type ResultCard, type ToolActivity } from "./api";

// --- safe rich text --------------------------------------------------------------------------------------------
/** A tiny Markdown subset (paragraphs, bullet/numbered lists, tables, **bold**, `code`) rendered as React elements.
 *  Never uses innerHTML, so model output can't inject markup. */
export function RichText({ text, className }: { text: string; className?: string }) {
  const blocks = text.trim().split(/\n{2,}/).filter(Boolean);
  return (
    <div className={cn("space-y-2 text-body text-fg", className)}>
      {blocks.map((block, i) => <Block key={i} block={block} />)}
    </div>
  );
}

function Block({ block }: { block: string }) {
  const lines = block.split("\n").filter((l) => l.trim() !== "");
  if (lines.length > 1 && lines.every((l) => l.trim().startsWith("|"))) {
    const rows = lines.filter((l) => !/^\s*\|?\s*:?-{2,}/.test(l)).map((l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
    const [head = [], ...body] = rows;
    return (
      <div className="overflow-x-auto rounded-[var(--radius-control)] border border-border">
        <table className="w-full text-small">
          <thead className="bg-surface-subtle"><tr>{head.map((c, j) => <th key={j} className="px-3 py-1.5 text-left font-medium text-fg-secondary"><Inline text={c} /></th>)}</tr></thead>
          <tbody>{body.map((r, j) => <tr key={j} className="border-t border-border-subtle">{r.map((c, k) => <td key={k} className="px-3 py-1.5 tabular"><Inline text={c} /></td>)}</tr>)}</tbody>
        </table>
      </div>
    );
  }
  if (lines.every((l) => /^\s*([-*•]|\d+\.)\s+/.test(l))) {
    const ordered = /^\s*\d+\./.test(lines[0] ?? "");
    const items = lines.map((l) => l.replace(/^\s*([-*•]|\d+\.)\s+/, ""));
    const List = ordered ? "ol" : "ul";
    return <List className={cn("space-y-1 pl-5", ordered ? "list-decimal" : "list-disc")}>{items.map((t, j) => <li key={j}><Inline text={t} /></li>)}</List>;
  }
  return (
    <p className="whitespace-pre-line break-words">
      {lines.map((l, j) => (
        <React.Fragment key={j}>{j > 0 && "\n"}<Inline text={l.replace(/^#{1,6}\s+/, "")} strong={/^#{1,6}\s/.test(l)} /></React.Fragment>
      ))}
    </p>
  );
}

function Inline({ text, strong }: { text: string; strong?: boolean }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  const nodes = parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**") ? <strong key={i} className="font-semibold">{p.slice(2, -2)}</strong>
      : p.startsWith("`") && p.endsWith("`") ? <code key={i} className="rounded bg-surface-sunken px-1 text-[0.9em]">{p.slice(1, -1)}</code>
        : <React.Fragment key={i}>{p}</React.Fragment>);
  return strong ? <strong className="font-semibold">{nodes}</strong> : <>{nodes}</>;
}

// --- tool activity & result cards ------------------------------------------------------------------------------
const TOOL_ICON = { ok: Check, denied: Ban, error: CircleAlert } as const;

export function ToolChips({ tools }: { tools: ToolActivity[] }) {
  if (!tools.length) return null;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Data used">
      {tools.map((t, i) => {
        const Icon = TOOL_ICON[t.status] ?? Check;
        return (
          <li key={`${t.name}-${i}`} title={t.summary ?? undefined}
            className={cn("inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-caption",
              t.status === "ok" ? "border-border bg-surface-subtle text-fg-secondary" : "border-warning/40 bg-warning/5 text-fg-secondary")}>
            <Icon className={cn("size-3 shrink-0", t.status === "ok" ? "text-success" : "text-warning")} aria-hidden />
            <span className="truncate">{t.label}{t.summary ? ` · ${t.summary}` : ""}</span>
            <span className="sr-only">({t.status === "ok" ? "succeeded" : t.status})</span>
          </li>
        );
      })}
    </ul>
  );
}

export function UnitCards({ units }: { units: PublicUnit[] }) {
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {units.map((u) => (
        <li key={`${u.project_code}-${u.code}`} className="rounded-[var(--radius-control)] border border-border bg-surface p-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-body font-semibold tabular">{u.code}</p>
              <p className="truncate text-caption text-fg-muted">{u.project}</p>
            </div>
            <StatusBadge status={u.status} />
          </div>
          <p className="mt-2 text-small text-fg-secondary">
            {humanize(u.type)} · {u.bedrooms === 0 ? "Studio" : `${u.bedrooms} BR`} · {Number(u.area_sqm).toFixed(0)} m² · Floor {u.floor}{u.view ? ` · ${u.view}` : ""}
          </p>
          <p className="mt-1 text-body font-semibold tabular">{formatMoney(u.list_price_sar)}</p>
        </li>
      ))}
    </ul>
  );
}

function TableCard({ card }: { card: Extract<ResultCard, { kind: "table" }> }) {
  return (
    <figure className="overflow-hidden rounded-[var(--radius-control)] border border-border">
      <figcaption className="border-b border-border-subtle bg-surface-subtle px-3 py-1.5 text-caption font-medium text-fg-secondary">{card.title}</figcaption>
      <div className="overflow-x-auto">
        <table className="w-full text-small">
          <thead><tr>{card.columns.map((c) => <th key={c} className="px-3 py-1.5 text-left font-medium text-fg-muted">{columnLabel(c)}</th>)}</tr></thead>
          <tbody>
            {card.rows.map((r, i) => (
              <tr key={i} className="border-t border-border-subtle">
                {card.columns.map((c) => <td key={c} className="px-3 py-1.5 tabular">{r[c] === null || r[c] === undefined ? "—" : String(r[c])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

export function ResultCards({ cards }: { cards: ResultCard[] }) {
  if (!cards.length) return null;
  return (
    <div className="space-y-2">
      {cards.map((c, i) =>
        c.kind === "units" ? <UnitCards key={i} units={c.units} />
          : c.kind === "table" ? <TableCard key={i} card={c} />
            : (
              <p key={i} className="flex items-center gap-2 rounded-[var(--radius-control)] border border-success/40 bg-success/5 px-3 py-2 text-small">
                <UserRoundCheck className="size-4 text-success" aria-hidden /> Your details were shared with our sales team.
              </p>
            ))}
    </div>
  );
}

// --- transcript ------------------------------------------------------------------------------------------------
export function Transcript({ messages, empty }: { messages: ChatMessage[]; empty?: React.ReactNode }) {
  const end = React.useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];
  React.useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [messages.length, last?.text, last?.tools.length]);
  if (!messages.length) return <>{empty}</>;
  return (
    <div className="space-y-5" aria-live="polite">
      {messages.map((m) => m.role === "user" ? (
        <div key={m.id} className="flex justify-end">
          <p className="max-w-[85%] whitespace-pre-line break-words rounded-[14px] rounded-br-[4px] bg-brand px-3.5 py-2 text-body text-on-accent">{m.text}</p>
        </div>
      ) : (
        <div key={m.id} className="space-y-2">
          <div className="flex items-center gap-2"><AiBadge />{m.status === "streaming" && <Loader2 className="size-3.5 animate-spin text-fg-muted motion-reduce:animate-none" aria-label="Answering" />}</div>
          <ToolChips tools={m.tools} />
          <ResultCards cards={m.cards} />
          {m.text ? <RichText text={m.text} /> : m.status === "streaming" && <p className="text-small text-fg-muted">{m.tools.length ? "Reading the data…" : "Thinking…"}</p>}
          {m.truncated && <p className="text-caption text-fg-muted">The answer was cut short.</p>}
          {m.status === "error" && (
            <p role="alert" className="flex items-start gap-2 rounded-[var(--radius-control)] border border-danger/40 bg-danger/5 px-3 py-2 text-small">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />{m.error}
            </p>
          )}
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}

export function Composer({ onSend, busy, disabled, placeholder, maxLength, footer }: {
  onSend: (text: string) => void; busy: boolean; disabled?: boolean; placeholder: string; maxLength: number; footer?: React.ReactNode;
}) {
  const [text, setText] = React.useState("");
  const submit = () => { if (text.trim() && !busy && !disabled) { onSend(text); setText(""); } };
  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="rounded-[var(--radius-panel)] border border-border bg-surface p-2 focus-within:border-border-strong">
      <label htmlFor="chat-input" className="sr-only">Message</label>
      <Textarea id="chat-input" value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} maxLength={maxLength} rows={2}
        disabled={disabled} className="min-h-0 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} />
      <div className="flex items-center justify-between gap-3 px-1 pt-1">
        <div className="min-w-0 text-caption text-fg-muted">{footer}</div>
        <Button type="submit" variant="primary" size="sm" loading={busy} disabled={disabled || !text.trim()} aria-label="Send message"><ArrowUp /> Send</Button>
      </div>
    </form>
  );
}

export function SuggestedPrompts({ prompts, onPick, disabled }: { prompts: string[]; onPick: (p: string) => void; disabled?: boolean }) {
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Suggested questions">
      {prompts.map((p) => (
        <li key={p}>
          <button type="button" disabled={disabled} onClick={() => onPick(p)}
            className="rounded-full border border-border bg-surface px-3 py-1.5 text-small text-fg-secondary transition-colors hover:border-border-strong hover:text-fg disabled:opacity-50">
            {p}
          </button>
        </li>
      ))}
    </ul>
  );
}
