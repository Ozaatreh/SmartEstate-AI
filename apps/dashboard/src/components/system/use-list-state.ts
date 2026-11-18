import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { ListQuery } from "@/lib/api-client";

export interface ListState<F extends string = string> {
  q: string;
  sort: string | undefined;
  page: number;
  pageSize: number;
  filters: Record<F, string | undefined>;
  activeFilterCount: number;
  query: ListQuery & Partial<Record<F, string>>;
  setQ: (q: string) => void;
  setSort: (sort: string | undefined) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  setFilter: (key: F, value: string | undefined) => void;
  clear: () => void;
}

/** The subset of list state the DataTable needs (independent of filter keys). */
export type TableListState = Pick<ListState<string>, "q" | "sort" | "page" | "pageSize" | "activeFilterCount" | "setQ" | "setSort" | "setPage" | "setPageSize" | "clear">;

/**
 * List state (search, sort, pagination, filters) lives in the URL query, so views are shareable
 * and survive reloads. Any change other than the page resets to page 1.
 */
export function useListState<F extends string = never>(opts: { filterKeys?: readonly F[]; defaultSort?: string; defaultPageSize?: number } = {}): ListState<F> {
  const { filterKeys = [] as readonly F[], defaultSort, defaultPageSize = 25 } = opts;
  const [params, setParams] = useSearchParams();

  const update = useCallback((patch: Record<string, string | undefined>, resetPage = true) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === "") next.delete(k);
        else next.set(k, v);
      }
      if (resetPage) next.delete("page");
      return next;
    }, { replace: true });
  }, [setParams]);

  return useMemo(() => {
    const q = params.get("q") ?? "";
    const sort = params.get("sort") ?? defaultSort;
    const page = Math.max(1, Number(params.get("page")) || 1);
    const pageSize = Number(params.get("page_size")) || defaultPageSize;
    const filters = Object.fromEntries(filterKeys.map((k) => [k, params.get(k) ?? undefined])) as Record<F, string | undefined>;
    const activeFilterCount = Object.values(filters).filter(Boolean).length;
    return {
      q, sort, page, pageSize, filters, activeFilterCount,
      query: { q: q || undefined, sort, page, page_size: pageSize, ...filters },
      setQ: (value) => update({ q: value.trim() || undefined }),
      setSort: (value) => update({ sort: value }),
      setPage: (value) => update({ page: value > 1 ? String(value) : undefined }, false),
      setPageSize: (value) => update({ page_size: value === defaultPageSize ? undefined : String(value) }),
      setFilter: (key, value) => update({ [key]: value }),
      clear: () => update({ q: undefined, ...Object.fromEntries(filterKeys.map((k) => [k, undefined])) }),
    };
  }, [params, filterKeys, defaultSort, defaultPageSize, update]);
}
