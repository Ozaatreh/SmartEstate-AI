import { Badge } from "@/components/system/badges";
import type { Lead } from "./api";

export function ScoreBadge({ lead }: { lead: Pick<Lead, "score" | "grade"> }) {
  if (lead.score === null) return <span className="text-small text-fg-muted">Scoring…</span>;
  return <Badge tone={lead.grade === "hot" ? "danger" : lead.grade === "warm" ? "warning" : "info"} dot={false}><span className="tabular">{lead.score}</span> · {lead.grade}</Badge>;
}
