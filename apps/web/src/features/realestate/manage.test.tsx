import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api-client";
import type { UnitDetail } from "./api";
import { changedFields, isPositiveAmount, parseAmenities, planShareError, unitIsCommitted } from "./logic";
import { BuildingFormDialog, PlanFormDialog, UnitFormDialog } from "./manage-dialogs";

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
afterEach(() => vi.restoreAllMocks());

const unit = (status: UnitDetail["status"]): UnitDetail => ({
  id: "u1", project: { id: "p1", code: "NOVA", name: "NOVA Residences" }, building: { id: "b1", code: "B", name: "Tower B" },
  unit_number: "301", unit_type: "apartment", bedrooms: 2, bathrooms: 2, floor: 3, area_sqm: "112.00", view: "Park",
  list_price: "935000.00", price_per_sqm: "8348.21", status, is_public: true, is_demo_data: true, notes: null, payment_plans: [],
  allowed_status_changes: [], can_manage: true, created_at: "2026-11-16T10:00:00Z", updated_at: "2026-11-16T10:00:00Z",
});

describe("inventory form rules", () => {
  it("validates payment-plan shares like the API", () => {
    expect(planShareError("10", "0", "36")).toBeNull();
    expect(planShareError("20", "30", "8")).toBeNull();
    expect(planShareError("100", "0", "0")).toBeNull();
    expect(planShareError("60", "50", "4")).toMatch(/cannot exceed 100%/);
    expect(planShareError("50", "0", "0")).toMatch(/add up to 100%/);
    expect(planShareError("101", "0", "1")).toMatch(/between 0 and 100/);
    expect(planShareError("10", "0", "2.5")).toMatch(/whole number/);
  });

  it("parses amenities, amounts and changed fields", () => {
    expect(parseAmenities("Pool\n Gym ,Pool\n\n")).toEqual(["Pool", "Gym"]);
    expect(isPositiveAmount("112.5") && isPositiveAmount("925000")).toBe(true);
    expect(isPositiveAmount("0") || isPositiveAmount("-1") || isPositiveAmount("1.234") || isPositiveAmount("abc")).toBe(false);
    expect(changedFields({ bedrooms: 2, view: null, area_sqm: "112.00" }, { bedrooms: 2, view: null, area_sqm: "112.00" })).toEqual({});
    expect(changedFields({ bedrooms: 2, view: null }, { bedrooms: 3, view: "Park" })).toEqual({ bedrooms: 3, view: "Park" });
    expect(unitIsCommitted("reserved") && unitIsCommitted("sold")).toBe(true);
    expect(unitIsCommitted("blocked")).toBe(false);
  });
});

describe("unit form", () => {
  it("locks commercial fields of a reserved unit and never sends them", async () => {
    const patch = vi.spyOn(api, "patch").mockResolvedValue(unit("reserved"));
    wrap(<UnitFormDialog unit={unit("reserved")} onClose={() => {}} />);
    expect(screen.getByText(/This unit is reserved/)).toBeInTheDocument();
    expect(screen.getByLabelText(/List price/)).toBeDisabled();
    expect(screen.getByLabelText(/Area/)).toBeDisabled();
    expect(screen.getByLabelText(/Bathrooms/)).toBeEnabled();
    expect(screen.queryByLabelText(/Start blocked/)).toBeNull(); // status never changes from this form
    const view = screen.getByLabelText(/View/);
    await userEvent.clear(view);
    await userEvent.type(view, "Boulevard");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(patch).toHaveBeenCalledWith("/realestate/units/u1", { view: "Boulevard" });
  });

  it("sends only changed fields for an available unit and validates numbers", async () => {
    const patch = vi.spyOn(api, "patch").mockResolvedValue(unit("available"));
    wrap(<UnitFormDialog unit={unit("available")} onClose={() => {}} />);
    const price = screen.getByLabelText(/List price/);
    await userEvent.clear(price);
    await userEvent.type(price, "-5");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(screen.getByText("A positive price in SAR.")).toBeInTheDocument();
    expect(patch).not.toHaveBeenCalled();
    await userEvent.clear(price);
    await userEvent.type(price, "950000");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(patch).toHaveBeenCalledWith("/realestate/units/u1", { list_price: "950000" });
  });
});

describe("plan and building forms", () => {
  it("blocks invalid shares before calling the API", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ id: "x", name: "Plan" });
    wrap(<PlanFormDialog projectId="p1" onClose={() => {}} />);
    await userEvent.type(screen.getByLabelText(/^Name/), "Cash");
    const down = screen.getByLabelText(/Down payment/);
    await userEvent.clear(down);
    await userEvent.type(down, "50");
    const n = screen.getByLabelText(/^Installments/);
    await userEvent.clear(n);
    await userEvent.type(n, "0");
    expect(screen.getByRole("alert")).toHaveTextContent(/add up to 100%/);
    expect(screen.getByRole("button", { name: /add plan/i })).toBeDisabled();
    await userEvent.clear(down);
    await userEvent.type(down, "100");
    await userEvent.click(screen.getByRole("button", { name: /add plan/i }));
    expect(post).toHaveBeenCalledWith("/realestate/projects/p1/payment-plans", expect.objectContaining({ name: "Cash", down_payment_pct: "100", installments: 0 }));
  });

  it("shows the API's rule when floors would drop below existing units", async () => {
    const { ApiError } = await import("@/lib/api-client");
    vi.spyOn(api, "patch").mockRejectedValue(new ApiError(422, { code: "floors_in_use", message: "Units exist up to floor 5; floors can't be lower.", request_id: "r" }));
    wrap(<BuildingFormDialog projectId="p1" building={{ id: "b1", project_id: "p1", code: "A", name: "Tower A", floors: 6, is_demo_data: true,
      units: { available: 1, reserved: 0, sold: 0, blocked: 0, total: 1 } }} onClose={() => {}} />);
    expect(screen.getByLabelText(/Code/)).toBeDisabled();
    const floors = screen.getByLabelText(/Floors/);
    await userEvent.clear(floors);
    await userEvent.type(floors, "3");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(await screen.findByText("Units exist up to floor 5; floors can't be lower.")).toBeInTheDocument();
  });
});
