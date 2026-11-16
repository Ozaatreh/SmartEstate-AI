import {
  flexRender, getCoreRowModel, useReactTable, type ColumnDef, type RowData, type VisibilityState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, Columns3, Search, X } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuTrigger, Select } from "@/components/ui/menu";
import type { Page } from "@/lib/api-client";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, TableSkeleton } from "./states";
import type { TableListState } from "./use-list-state";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    /** Server sort key; makes the header sortable. */
    sortKey?: string;
    align?: "left" | "right";
    /** Hide below this breakpoint in the desktop table (mobile uses stacked rows). */
    className?: string;
    label?: string;
  }
}

export interface DataTableProps<T> {
  columns: ColumnDef<T, unknown>[];
  page: Page<T> | undefined;
  isLoading: boolean;
  isFetching?: boolean;
  error?: unknown;
  onRetry?: () => void;
  state: TableListState;
  searchPlaceholder?: string;
  /** Extra filter controls rendered in the FilterBar. */
  filters?: React.ReactNode;
  empty?: React.ReactNode;
  getRowId: (row: T) => string;
  onRowClick?: (row: T) => void;
  /** Stacked row renderer for small screens. */
  mobileRow: (row: T) => React.ReactNode;
  pageSizes?: number[];
  ariaLabel: string;
}

/** Server-driven table: search, filters, sort, pagination, column visibility, all states. */
export function DataTable<T>(props: DataTableProps<T>) {
  const {
    columns, page, isLoading, isFetching, error, onRetry, state, searchPlaceholder = "Search…", filters, empty,
    getRowId, onRowClick, mobileRow, pageSizes = [10, 25, 50, 100], ariaLabel,
  } = props;
  const [visibility, setVisibility] = React.useState<VisibilityState>({});
  const table = useReactTable({
    data: page?.items ?? [],
    columns,
    getRowId,
    state: { columnVisibility: visibility },
    onColumnVisibilityChange: setVisibility,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
  });

  const hasRows = (page?.items.length ?? 0) > 0;
  const filtered = Boolean(state.q) || state.activeFilterCount > 0;

  const toggleSort = (key: string) => {
    const current = state.sort;
    state.setSort(current === key ? `-${key}` : current === `-${key}` ? undefined : key);
  };

  return (
    <div className="overflow-hidden rounded-[var(--radius-panel)] border border-border bg-surface">
      {/* FilterBar */}
      <div className="flex flex-col gap-2 border-b border-border-subtle p-3 md:flex-row md:items-center">
        <SearchInput value={state.q} onChange={state.setQ} placeholder={searchPlaceholder} />
        {filters && <div className="flex flex-wrap items-center gap-2">{filters}</div>}
        <div className="flex items-center gap-2 md:ml-auto">
          {filtered && (
            <Button size="sm" variant="ghost" onClick={state.clear}><X /> Clear</Button>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="ghost" className="hidden md:inline-flex" aria-label="Choose columns"><Columns3 /> Columns</Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuLabel>Visible columns</DropdownMenuLabel>
              {table.getAllLeafColumns().filter((c) => c.getCanHide() && c.columnDef.meta?.label).map((c) => (
                <DropdownMenuCheckboxItem key={c.id} checked={c.getIsVisible()} onCheckedChange={(v) => c.toggleVisibility(Boolean(v))} onSelect={(e) => e.preventDefault()}>
                  {c.columnDef.meta?.label}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Body */}
      {isLoading ? (
        <TableSkeleton columns={Math.min(columns.length, 5)} />
      ) : error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : !hasRows ? (
        filtered ? <EmptyState filtered onClearFilters={state.clear} /> : (empty ?? <EmptyState />)
      ) : (
        <div className={cn("transition-opacity duration-150", isFetching && "opacity-60")}>
          {/* Desktop / tablet */}
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full border-collapse text-body" aria-label={ariaLabel} aria-busy={isFetching || undefined}>
              <thead className="sticky top-0 z-10 bg-surface-subtle">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id} className="border-b border-border">
                    {hg.headers.map((h) => {
                      const meta = h.column.columnDef.meta;
                      const sortKey = meta?.sortKey;
                      const dir = state.sort === sortKey ? "asc" : state.sort === `-${sortKey}` ? "desc" : null;
                      return (
                        <th key={h.id} scope="col"
                          aria-sort={sortKey ? (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none") : undefined}
                          className={cn("h-9 whitespace-nowrap px-4 text-left text-caption font-medium uppercase tracking-[0.04em] text-fg-muted", meta?.align === "right" && "text-right", meta?.className)}>
                          {h.isPlaceholder ? null : sortKey ? (
                            <button type="button" onClick={() => toggleSort(sortKey)}
                              className={cn("-mx-1 inline-flex items-center gap-1 rounded px-1 uppercase tracking-[0.04em] transition-colors hover:text-fg", dir && "text-fg", meta?.align === "right" && "flex-row-reverse")}>
                              {flexRender(h.column.columnDef.header, h.getContext())}
                              {dir === "asc" ? <ArrowUp className="size-3" /> : dir === "desc" ? <ArrowDown className="size-3" /> : <ChevronsUpDown className="size-3 opacity-50" />}
                            </button>
                          ) : flexRender(h.column.columnDef.header, h.getContext())}
                        </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id}
                    onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                    className={cn("h-10 transition-colors duration-150 hover:bg-surface-subtle", onRowClick && "cursor-pointer")}>
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className={cn("px-4 py-2 align-middle", cell.column.columnDef.meta?.align === "right" && "text-right", cell.column.columnDef.meta?.className)}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Mobile: stacked rows */}
          <ul className="divide-y divide-border-subtle md:hidden" aria-label={ariaLabel}>
            {page!.items.map((item) => (
              <li key={getRowId(item)}>
                {onRowClick ? (
                  <button type="button" onClick={() => onRowClick(item)} className="block w-full px-4 py-3 text-left transition-colors active:bg-surface-subtle">{mobileRow(item)}</button>
                ) : <div className="px-4 py-3">{mobileRow(item)}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Pagination */}
      {page && hasRows && !error && (
        <div className="flex flex-col gap-2 border-t border-border-subtle px-4 py-2.5 text-small text-fg-secondary sm:flex-row sm:items-center sm:justify-between">
          <span className="tabular">
            {formatNumber((page.page - 1) * page.page_size + 1)}–{formatNumber(Math.min(page.page * page.page_size, page.total))} of {formatNumber(page.total)}
          </span>
          <div className="flex items-center gap-2">
            <span className="hidden sm:inline">Rows</span>
            <Select aria-label="Rows per page" className="h-8 w-[72px]" value={String(state.pageSize)} onValueChange={(v) => state.setPageSize(Number(v))}
              options={pageSizes.map((s) => ({ value: String(s), label: String(s) }))} />
            <span className="tabular px-1">Page {page.page} of {page.pages}</span>
            <Button size="icon" variant="ghost" aria-label="Previous page" disabled={page.page <= 1} onClick={() => state.setPage(page.page - 1)}><ChevronLeft /></Button>
            <Button size="icon" variant="ghost" aria-label="Next page" disabled={page.page >= page.pages} onClick={() => state.setPage(page.page + 1)}><ChevronRight /></Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Debounced (300 ms) search box bound to list state. */
export function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  const [text, setText] = React.useState(value);
  const [prevValue, setPrevValue] = React.useState(value);
  if (value !== prevValue) {  // external change (e.g. "Clear filters")
    setPrevValue(value);
    setText(value);
  }
  React.useEffect(() => {
    if (text === value) return;
    const t = window.setTimeout(() => onChange(text), 300);
    return () => window.clearTimeout(t);
  }, [text, value, onChange]);
  return (
    <div className="relative w-full md:max-w-xs">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-muted" aria-hidden />
      <Input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label={placeholder} className="h-8 pl-8" />
    </div>
  );
}
