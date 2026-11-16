import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api-client";
import type { PurchaseOrderDetail } from "./api";
import { CancelOrderDialog } from "./order-dialogs";
import { budgetNote } from "./orders-logic";

const order: PurchaseOrderDetail = {
  id: "po-1", code: "PO-00001", status: "issued", total_amount: "11002.00", supplier: { id: "s", code: "SUP-1", name: "Fictional Supplies" },
  request_id: "pr-1", request_code: "PR-00008", request_title: "Site pumps", request_status: "approved", expected_delivery_date: null,
  issued_at: "2026-11-16T10:00:00Z", cancelled_at: null, budget_released: false, created_at: "2026-11-16T09:00:00Z", payment_terms: null,
  delivery_address: null, notes: null, lines: [], cancel_reason: null, created_by: "Buyer", issued_by: "Buyer", cancelled_by: null,
  replaces: null, replaced_by: null, committed_amount: "11002.00", released_amount: null, allowed_actions: ["cancel"],
};

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);

afterEach(() => vi.restoreAllMocks());

describe("purchase order budget wording", () => {
  it("explains the single commitment for each state", () => {
    expect(budgetNote(order).text).toMatch(/no second commitment/);
    expect(budgetNote({ ...order, status: "cancelled", budget_released: true }).text).toMatch(/Released/);
    expect(budgetNote({ ...order, status: "cancelled", budget_released: false }).text).toMatch(/replacement/);
  });
});

describe("cancel order dialog", () => {
  it("requires an explicit budget decision and a reason before calling the API", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ ...order, status: "cancelled" });
    wrap(<CancelOrderDialog order={order} onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /cancel order/i }));
    expect(screen.getByText("Choose what happens to the committed budget.")).toBeInTheDocument();
    expect(screen.getByText(/at least 3 characters/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("sends release_budget according to the chosen option", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ ...order, status: "cancelled" });
    const onClose = vi.fn();
    wrap(<CancelOrderDialog order={order} onClose={onClose} />);
    await userEvent.click(screen.getByLabelText(/keep the budget for a replacement order/i));
    await userEvent.type(screen.getByLabelText(/reason/i), "Wrong delivery site");
    await userEvent.click(screen.getByRole("button", { name: /cancel order/i }));
    expect(post).toHaveBeenCalledWith("/procurement/purchase-orders/po-1/cancel", { reason: "Wrong delivery site", release_budget: false });
    expect(onClose).toHaveBeenCalled();
  });
});
