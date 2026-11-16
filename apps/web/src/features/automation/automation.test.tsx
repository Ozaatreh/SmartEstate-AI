import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ExecutionStatusBadge, TriggerLabel, TriggerSummary } from "./shared";
import { entityLink, formatDuration } from "./format";

describe("automation helpers", () => {
  it("formats durations", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(420)).toBe("420 ms");
    expect(formatDuration(2500)).toBe("2.5 s");
    expect(formatDuration(125_000)).toBe("2 min 5 s");
  });

  it("links executions to their business records", () => {
    expect(entityLink("purchase_request", "x")).toBe("/procurement/requests/x");
    expect(entityLink("budget", "y")).toBe("/finance/budgets/y");
    expect(entityLink("lead", "z")).toBeNull();
    expect(entityLink("budget", null)).toBeNull();
  });
});

describe("status and trigger display", () => {
  const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);

  it("shows retries distinctly from first-time queued runs", () => {
    const { rerender } = wrap(<ExecutionStatusBadge status="pending" attempt={1} maxAttempts={3} />);
    expect(screen.getByText("Retry 2/3")).toBeInTheDocument();
    rerender(<QueryClientProvider client={new QueryClient()}><MemoryRouter><ExecutionStatusBadge status="pending" attempt={0} /></MemoryRouter></QueryClientProvider>);
    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  it("describes event and schedule triggers", () => {
    wrap(<>
      <TriggerSummary workflow={{ event_types: ["lead.created"], schedule_minutes: 15 }} />
      <TriggerLabel execution={{ trigger_type: "manual", event_type: null }} />
    </>);
    expect(screen.getByText("lead.created")).toBeInTheDocument();
    expect(screen.getByText("Every 15 min")).toBeInTheDocument();
    expect(screen.getByText("Manual")).toBeInTheDocument();
  });
});
