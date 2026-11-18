import { Info } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/system/badges";
import { MoneyText } from "@/components/system/data-display";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Availability, GridUnit, StatusCounts } from "./api";
import { DEMO_LABEL, UNIT_STATUS_STYLE, bedroomsLabel } from "./logic";

/** Every NOVA screen says plainly that the property data is invented. */
export function DemoDataNotice({ className }: { className?: string }) {
  return (
    <p role="note" className={cn("mb-4 flex items-start gap-2 rounded-[var(--radius-panel)] border border-warning/30 bg-warning-subtle px-3 py-2 text-small text-fg-secondary", className)}>
      <Info className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
      <span><span className="font-medium text-fg">{DEMO_LABEL}.</span> NOVA Residences, its buildings, units, prices and payment plans are fictional and exist only for this prototype.</span>
    </p>
  );
}

export function DemoBadge() {
  return <Badge tone="warning" dot={false}>{DEMO_LABEL}</Badge>;
}

export function StatusLegend({ counts, className }: { counts?: StatusCounts; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 text-small text-fg-secondary", className)} aria-label="Unit status legend">
      {(["available", "reserved", "sold", "blocked"] as const).map((s) => (
        <li key={s} className="flex items-center gap-1.5">
          <span aria-hidden className={cn("size-3 rounded-sm border", UNIT_STATUS_STYLE[s])} />
          <span className="capitalize">{s}</span>
          {counts && <span className="tabular text-fg-muted">{counts[s]}</span>}
        </li>
      ))}
    </ul>
  );
}

function UnitTile({ unit }: { unit: GridUnit }) {
  return (
    <Link
      to={`/realestate/units/${unit.id}`}
      className={cn("flex w-[104px] shrink-0 flex-col rounded-[var(--radius-control)] border px-2 py-1.5 text-left transition-colors focus-visible:outline-2", UNIT_STATUS_STYLE[unit.status])}
      aria-label={`Unit ${unit.unit_number}, ${bedroomsLabel(unit.bedrooms)}, ${unit.status}, ${formatMoney(unit.list_price)}`}
    >
      <span className="tabular text-small font-semibold">{unit.unit_number}</span>
      <span className="text-caption text-fg-secondary">{bedroomsLabel(unit.bedrooms)} · {Number(unit.area_sqm).toLocaleString("en-US")} m²</span>
      <MoneyText value={unit.list_price} className="text-caption text-fg" />
    </Link>
  );
}

/** Building × floor availability grid. Wide floors scroll inside their panel, never the page. */
export function AvailabilityGrid({ data }: { data: Availability }) {
  if (!data.buildings.length) return <p className="p-4 text-small text-fg-muted">No buildings yet.</p>;
  return (
    <div className="space-y-4">
      {data.buildings.map((b) => (
        <section key={b.id} className="rounded-[var(--radius-panel)] border border-border bg-surface" aria-label={`${b.name} availability`}>
          <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle px-4 py-3">
            <div>
              <h3 className="text-body font-semibold">{b.name} <span className="tabular font-normal text-fg-muted">· {b.code}</span></h3>
              <p className="text-small text-fg-muted">{b.floors} floors · {b.units.total} units</p>
            </div>
            <StatusLegend counts={b.units} />
          </header>
          {b.rows.length === 0 ? (
            <p className="p-4 text-small text-fg-muted">No units in this building yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-separate border-spacing-0 text-left">
                <tbody>
                  {b.rows.map((row) => (
                    <tr key={row.floor}>
                      <th scope="row" className="sticky left-0 w-16 border-b border-border-subtle bg-surface px-3 py-2 align-middle text-caption font-medium text-fg-muted">
                        {row.floor === 0 ? "G" : `F${row.floor}`}
                      </th>
                      <td className="border-b border-border-subtle px-2 py-2">
                        <div className="flex gap-2">{row.units.map((u) => <UnitTile key={u.id} unit={u} />)}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ))}
    </div>
  );
}

const BAR_COLOR: Record<string, string> = { sold: "bg-brand", reserved: "bg-warning", available: "bg-success", blocked: "bg-border-strong" };

/** Stacked share of units by status (never colour alone: the legend carries the numbers). */
export function StatusBar({ counts, className }: { counts: StatusCounts; className?: string }) {
  const total = Math.max(1, counts.total);
  return (
    <div className={cn("flex h-2 w-full overflow-hidden rounded-full bg-surface-sunken", className)} role="img"
      aria-label={`${counts.available} available, ${counts.reserved} reserved, ${counts.sold} sold, ${counts.blocked} blocked`}>
      {(["sold", "reserved", "available", "blocked"] as const).map((s) => counts[s] > 0 && (
        <span key={s} className={BAR_COLOR[s]} style={{ width: `${(counts[s] / total) * 100}%` }} />
      ))}
    </div>
  );
}
