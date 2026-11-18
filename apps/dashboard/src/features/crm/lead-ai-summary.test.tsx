import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api-client";
import type { AIStatus, LeadSummary } from "./api";
import { LeadAISummary } from "./lead-ai-summary";

const wrap = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
    <LeadAISummary leadId="l1" />
  </QueryClientProvider>,
);
afterEach(() => vi.restoreAllMocks());

const usable: AIStatus = { state: "unverified", reason: "AI is configured.", usable: true };
const summary = (overview: string): LeadSummary => ({
  lead_id: "l1", lead_code: "LEAD-00009", ai_generated: true,
  advisory_notice: "AI-generated and advisory only. Check it against the record before acting; it changes nothing.",
  overview, buying_signals: ["Asked for a second viewing."], concerns: ["Financing not confirmed."],
  next_action: "Confirm financing with the buyer.", next_action_reason: "It is the main open question.",
  generated_at: new Date().toISOString(), model: "test-model", request_id: "r1", interactions_considered: 3,
});
const aiError = (code: string, message: string) => new ApiError(503, { code, message, details: {}, request_id: "req12345678" } as never);

describe("AI lead summary", () => {
  it("generates on request, labels it as AI-generated advisory output and regenerates", async () => {
    vi.spyOn(api, "get").mockResolvedValue(usable);
    const post = vi.spyOn(api, "post").mockResolvedValueOnce(summary("First overview.")).mockResolvedValueOnce(summary("Second overview."));
    wrap();
    expect(screen.getAllByText("AI-generated").length).toBeGreaterThan(0);
    await userEvent.click(await screen.findByRole("button", { name: /generate summary/i }));
    expect(post).toHaveBeenCalledWith("/crm/leads/l1/ai-summary");
    expect(await screen.findByText("First overview.")).toBeInTheDocument();
    expect(screen.getByText("Asked for a second viewing.")).toBeInTheDocument();
    expect(screen.getByText("Financing not confirmed.")).toBeInTheDocument();
    expect(screen.getByText("Confirm financing with the buyer.")).toBeInTheDocument();
    expect(screen.getByText(/advisory only/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /regenerate ai summary/i }));
    expect(await screen.findByText("Second overview.")).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(2);
  });

  it("shows an unavailable notice and no generate button when AI is disabled", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ state: "disabled", reason: "AI features are turned off (AI_ENABLED=false).", usable: false });
    const post = vi.spyOn(api, "post");
    wrap();
    expect(await screen.findByRole("status")).toHaveTextContent(/unavailable right now.*works as usual/i);
    expect(screen.queryByRole("button", { name: /generate summary/i })).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("reports a failed generation with a retry, keeping the previous summary", async () => {
    vi.spyOn(api, "get").mockResolvedValue(usable);
    vi.spyOn(api, "post")
      .mockResolvedValueOnce(summary("Kept overview."))
      .mockRejectedValueOnce(aiError("ai_rate_limited", "The AI provider is busy. Try again shortly."))
      .mockResolvedValueOnce(summary("Fresh overview."));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: /generate summary/i }));
    await screen.findByText("Kept overview.");
    await userEvent.click(screen.getByRole("button", { name: /regenerate ai summary/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/busy.*previous run/i);
    expect(screen.getByText("Kept overview.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(screen.getByText("Fresh overview.")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("falls back to the unavailable notice when the backend reports AI is turned off", async () => {
    vi.spyOn(api, "get").mockResolvedValue(usable);
    vi.spyOn(api, "post").mockRejectedValue(aiError("ai_disabled", "AI features are turned off."));
    wrap();
    await userEvent.click(await screen.findByRole("button", { name: /generate summary/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/unavailable right now/i);
  });
});
