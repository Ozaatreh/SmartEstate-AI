import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AvailabilityGrid, DemoDataNotice, StatusBar } from "@/features/realestate/shared";
import { bedroomsLabel } from "@/features/realestate/logic";
import { api } from "@/lib/api-client";
import { formatMoney } from "@/lib/format";
import type { LeadDetail } from "./api";
import { budgetLabel, fromLocalInput, stageLabel, stageNeedsReason, stageProgress, timelineLabel, toLocalInput } from "./crm-logic";
import { StageDialog } from "./lead-dialogs";

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
afterEach(() => vi.restoreAllMocks());

const lead = {
  id: "l1", code: "LEAD-00009", full_name: "Fictional Buyer", stage: "viewing", allowed_stages: ["negotiation", "won", "lost"],
} as unknown as LeadDetail;

describe("CRM helpers", () => {
  it("labels stages, timelines and budgets", () => {
    expect(stageLabel("negotiation")).toBe("Negotiation");
    expect(timelineLabel("within_3_months")).toBe("Within 3 months");
    expect(timelineLabel(null)).toBe("—");
    const f = (v: string) => formatMoney(v);
    expect(budgetLabel("900000", "1500000", f)).toBe("SAR 900,000 – SAR 1,500,000");
    expect(budgetLabel(null, "800000", f)).toBe("Up to SAR 800,000");
    expect(budgetLabel(null, null, f)).toBe("—");
  });

  it("knows which stages need a reason and where a stage sits on the pipeline", () => {
    expect(stageNeedsReason("won") && stageNeedsReason("lost")).toBe(true);
    expect(stageNeedsReason("qualified")).toBe(false);
    expect(stageProgress("new")).toBe(0);
    expect(stageProgress("won")).toBe(5);
    expect(stageProgress("lost")).toBe(-1);
  });

  it("round-trips datetime-local values", () => {
    const iso = "2026-12-01T09:30:00.000Z";
    expect(fromLocalInput(toLocalInput(iso))).toBe(iso);
    expect(fromLocalInput("")).toBeNull();
    expect(toLocalInput(null)).toBe("");
  });
});

describe("stage dialog", () => {
  it("requires a reason to close a lead before calling the API", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({});
    wrap(<StageDialog lead={lead} target="lost" onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /move to lost/i }));
    expect(screen.getByText(/at least 3 characters/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/reason/i), "Bought elsewhere");
    await userEvent.click(screen.getByRole("button", { name: /move to lost/i }));
    expect(post).toHaveBeenCalledWith("/crm/leads/l1/stage", { stage: "lost", reason: "Bought elsewhere" });
  });

  it("lets forward moves go without a reason", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({});
    wrap(<StageDialog lead={lead} target="negotiation" onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /move to negotiation/i }));
    expect(post).toHaveBeenCalledWith("/crm/leads/l1/stage", { stage: "negotiation", reason: null });
  });
});

describe("real estate display", () => {
  it("labels fictional data and summarises status", () => {
    wrap(<><DemoDataNotice /><StatusBar counts={{ available: 3, reserved: 1, sold: 1, blocked: 0, total: 5 }} /></>);
    expect(screen.getByRole("note")).toHaveTextContent("Illustrative / Fictional Demo Data");
    expect(screen.getByRole("img", { name: "3 available, 1 reserved, 1 sold, 0 blocked" })).toBeInTheDocument();
    expect(bedroomsLabel(0)).toBe("Studio");
  });

  it("renders the building × floor grid with linked units", () => {
    wrap(<AvailabilityGrid data={{
      project: { id: "p", code: "NOVA", name: "NOVA" },
      totals: { available: 1, reserved: 1, sold: 0, blocked: 0, total: 2 },
      buildings: [{
        id: "b", code: "A", name: "Tower A", floors: 2, units: { available: 1, reserved: 1, sold: 0, blocked: 0, total: 2 },
        rows: [
          { floor: 2, units: [{ id: "u2", unit_number: "201", unit_type: "apartment", bedrooms: 2, area_sqm: "110.00", list_price: "900000.00", status: "reserved" }] },
          { floor: 1, units: [{ id: "u1", unit_number: "101", unit_type: "studio", bedrooms: 0, area_sqm: "45.00", list_price: "420000.00", status: "available" }] },
        ],
      }],
    }} />);
    expect(screen.getByRole("link", { name: /Unit 201, 2 BR, reserved, SAR 900,000/ })).toHaveAttribute("href", "/realestate/units/u2");
    expect(screen.getByRole("rowheader", { name: "F1" })).toBeInTheDocument();
  });
});
