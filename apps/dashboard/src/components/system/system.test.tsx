import type { ColumnDef } from "@tanstack/react-table";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import { StatusBadge } from "./badges";
import { DataTable } from "./data-table";
import type { TableListState } from "./use-list-state";

interface Row { id: string; name: string }
const columns: ColumnDef<Row, unknown>[] = [{ id: "name", header: "Name", meta: { sortKey: "name", label: "Name" }, cell: ({ row }) => row.original.name }];

function state(overrides: Partial<TableListState> = {}): TableListState {
  return {
    q: "", sort: undefined, page: 1, pageSize: 25, activeFilterCount: 0,
    setQ: vi.fn(), setSort: vi.fn(), setPage: vi.fn(), setPageSize: vi.fn(), clear: vi.fn(), ...overrides,
  };
}

function renderTable(props: Partial<React.ComponentProps<typeof DataTable<Row>>>) {
  return render(
    <MemoryRouter>
      <DataTable<Row> ariaLabel="People" columns={columns} page={undefined} isLoading={false} state={state()}
        getRowId={(r) => r.id} mobileRow={(r) => r.name} {...props} />
    </MemoryRouter>,
  );
}

describe("DataTable", () => {
  it("renders a loading skeleton", () => {
    renderTable({ isLoading: true });
    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
  });

  it("renders the error state with retry and request id", async () => {
    const onRetry = vi.fn();
    renderTable({ error: new ApiError(500, { code: "internal_error", message: "Boom", request_id: "abcdef123456" }), onRetry });
    expect(screen.getByText("Boom")).toBeInTheDocument();
    expect(screen.getByText(/Ref abcdef12/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("renders a permission state for 403 errors", () => {
    renderTable({ error: new ApiError(403, { code: "permission_denied", message: "No" }) });
    expect(screen.getByText("You don't have access to this")).toBeInTheDocument();
  });

  it("distinguishes empty from filtered-empty", async () => {
    const clear = vi.fn();
    const { unmount } = renderTable({ page: { items: [], total: 0, page: 1, page_size: 25, pages: 1 } });
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
    unmount();
    renderTable({ page: { items: [], total: 0, page: 1, page_size: 25, pages: 1 }, state: state({ q: "zzz", clear }) });
    expect(screen.getByText("No matching results")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(clear).toHaveBeenCalled();
  });

  it("cycles server sort asc → desc → none from the header", async () => {
    const setSort = vi.fn();
    const page = { items: [{ id: "1", name: "Layla" }], total: 1, page: 1, page_size: 25, pages: 1 };
    const { rerender } = renderTable({ page, state: state({ setSort }) });
    await userEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(setSort).toHaveBeenLastCalledWith("name");
    rerender(<MemoryRouter><DataTable<Row> ariaLabel="People" columns={columns} page={page} isLoading={false} state={state({ setSort, sort: "name" })} getRowId={(r) => r.id} mobileRow={(r) => r.name} /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(setSort).toHaveBeenLastCalledWith("-name");
    expect(screen.getByRole("columnheader", { name: /Name/ })).toHaveAttribute("aria-sort", "ascending");
  });
});

describe("StatusBadge", () => {
  it("shows a text label, not colour alone", () => {
    render(<StatusBadge status="pending_approval" />);
    expect(screen.getByText("Pending approval")).toBeInTheDocument();
  });
});
