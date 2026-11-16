import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DecisionDialog } from "@/features/approvals/decision-dialog";
import type { ApprovalDetail } from "@/features/approvals/api";
import { ApprovalTimeline, BudgetImpactCard } from "./business";

const position = { allocated: "100000.00", adjustments: "0.00", committed: "40000.00", actual: "0.00", available: "60000.00", utilisation_pct: "40.0" };

describe("BudgetImpactCard", () => {
  it("shows the available amount after this request, from exact API strings", () => {
    render(<MemoryRouter><BudgetImpactCard impact={{ found: true, scope_label: "Construction department", category: "Equipment", fiscal_year: 2026, position,
      amount: "25000.50", available_after: "34999.50", over_budget: false, approval_levels: ["Department manager"] }} /></MemoryRouter>);
    expect(screen.getByText("SAR 34,999.50")).toBeInTheDocument();
    expect(screen.getByText("SAR 100,000")).toBeInTheDocument();
    expect(screen.getByText(/Department manager/)).toBeInTheDocument();
    expect(screen.queryByText(/Exceeds the available budget/)).not.toBeInTheDocument();
  });

  it("warns when over budget and when no budget exists", () => {
    const { rerender } = render(<MemoryRouter><BudgetImpactCard impact={{ found: true, scope_label: "X", category: "Equipment", fiscal_year: 2026, position,
      amount: "70000.00", available_after: "-10000.00", over_budget: true, approval_levels: ["Department manager", "Finance", "Executive"] }} /></MemoryRouter>);
    expect(screen.getByText(/Exceeds the available budget/)).toBeInTheDocument();
    rerender(<MemoryRouter><BudgetImpactCard impact={{ found: false, scope_label: "IT department", category: "Technology", fiscal_year: 2026, position: null,
      amount: "1.00", available_after: null, over_budget: true, approval_levels: [] }} /></MemoryRouter>);
    expect(screen.getByText("No budget found")).toBeInTheDocument();
  });
});

describe("ApprovalTimeline", () => {
  it("shows decisions, comments and escalation reasons", () => {
    render(<ApprovalTimeline steps={[
      { step_order: 1, label: "Department manager", status: "approved", assignee: { full_name: "Faisal" }, pool_label: null,
        escalation_reason: "Requester manages the department; escalated to Faisal.", activated_at: null, decided_at: new Date().toISOString(),
        decision: { decision: "approved", comment: "Go ahead", decided_by: { full_name: "Faisal" }, created_at: new Date().toISOString() } },
      { step_order: 2, label: "Finance", status: "pending", assignee: null, pool_label: "Finance approvers", escalation_reason: null, activated_at: new Date().toISOString(), decided_at: null, decision: null },
    ]} />);
    expect(screen.getByText(/Approved by Faisal/)).toBeInTheDocument();
    expect(screen.getByText(/“Go ahead”/)).toBeInTheDocument();
    expect(screen.getByText(/escalated to Faisal/)).toBeInTheDocument();
    expect(screen.getByText(/Assigned to Finance approvers/)).toBeInTheDocument();
  });
});

describe("DecisionDialog", () => {
  afterEach(() => vi.unstubAllGlobals());
  const approval: ApprovalDetail = {
    id: "a1", entity_type: "purchase_request", entity_label: "Purchase request", entity_id: "p1", entity_code: "PR-00012", title: "Concrete pump",
    amount: "160500.00", status: "pending", flags: {}, requester: { id: "u", full_name: "Ahmed" }, current_step: 2, current_step_label: "Finance",
    waiting_on: "Finance approvers", link: "/procurement/requests/p1", created_at: "", completed_at: null, can_decide: true, policy_name: "SAR 50,000 – 250,000",
    allowed_actions: ["approve", "reject"], blocked_reason: null,
    steps: [{ step_order: 2, level: "finance", label: "Finance", status: "pending", assignee: null, pool_label: "Finance approvers", escalation_reason: null, activated_at: null, decided_at: null, decision: null }],
  };
  const wrap = (ui: React.ReactNode) => <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>;

  it("requires a comment to reject and never calls the API without one", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(wrap(<DecisionDialog approval={approval} decision="reject" onClose={() => undefined} />));
    expect(screen.getByText("SAR 160,500.00")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Reject request/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Explain why/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the approval with the comment and closes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...approval, status: "approved" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const onClose = vi.fn();
    render(wrap(<DecisionDialog approval={approval} decision="approve" onClose={onClose} />));
    expect(screen.getByText(/final approval/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Comment/), "Budget confirmed");
    await userEvent.click(screen.getByRole("button", { name: /Approve/ }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/approvals/a1/approve");
    expect(JSON.parse(String(init.body))).toEqual({ comment: "Budget confirmed" });
  });
});
