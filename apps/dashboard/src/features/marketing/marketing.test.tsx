import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Campaign, ContentDetail } from "./api";
import ContentEditorPage from "./content-editor-page";
import { contentProblems, parseHashtags, totalLength } from "./logic";
import { ContentPreview } from "./preview";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubFetch(routes: Record<string, (init?: RequestInit) => Response>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const key = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => url.includes(k));
    return key ? routes[key]!(init) : json({ error: { code: "not_found", message: "Not found" } }, 404);
  }));
  return calls;
}

const wrap = (path: string) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/marketing/content/new" element={<ContentEditorPage />} />
        <Route path="/marketing/content/:id" element={<ContentEditorPage />} />
      </Routes>
    </MemoryRouter>
  </QueryClientProvider>,
);

const CAMPAIGN: Campaign = {
  id: "c1", code: "MC-00001", name: "NOVA spring launch", objective: "Viewings", description: null, project: { id: "p1", code: "NOVA", name: "NOVA Residences" },
  channels: ["instagram", "x", "email"], start_date: null, end_date: null, status: "active", created_by: null, created_at: "", updated_at: "",
  content: { draft: 0, pending_approval: 0, approved: 0, rejected: 0, archived: 0 }, allowed_actions: ["edit", "archive", "add_content"],
};
const FACTS = {
  project: CAMPAIGN.project, city: "Riyadh", district: null, status: "launched", handover_date: "2028-12-31", is_published: true, is_demo_data: true,
  amenities: ["Swimming pool"], available_units: 20, price_from_sar: "435000.00", description: null,
  bedroom_options: [{ bedrooms: 2, available: 6, price_from_sar: "910000.00", price_to_sar: "1020000.00" }], payment_plans: [],
};
const AI_OFF = { enabled: false, reason: "AI drafting is turned off (AI_MARKETING_STUDIO_ENABLED=false). Write and edit content manually." };

function detail(over: Partial<ContentDetail> = {}): ContentDetail {
  return {
    id: "m1", code: "MCT-00001", campaign: { id: "c1", code: "MC-00001", name: CAMPAIGN.name }, project: CAMPAIGN.project, channel: "instagram",
    language: "ar", headline: "حياة في نوفا", body: "شقق بغرفتي نوم.", call_to_action: "احجز زيارتك", hashtags: ["#الرياض"], status: "pending_approval",
    version: 2, generated_by_ai: false, created_by: { id: "u1", full_name: "Lina Specialist" }, updated_at: new Date().toISOString(),
    submitted_at: new Date().toISOString(), decided_at: null, rejection_comment: null, allowed_actions: [], approval_id: "a1", can_decide: false,
    decide_blocked_reason: "You can't approve a request you submitted.",
    approvals: [{ id: "a1", status: "pending", version: 2, requested_by: { id: "u1", full_name: "Lina Specialist" }, created_at: new Date().toISOString(), completed_at: null,
      steps: [{ label: "Marketing manager", status: "pending", decided_by: null, decided_at: null, comment: null }] }],
    versions: [
      { version: 2, channel: "instagram", language: "ar", headline: "حياة في نوفا", body: "شقق بغرفتي نوم.", call_to_action: null, hashtags: [], note: "Edited", edited_by: null, created_at: new Date().toISOString() },
      { version: 1, channel: "instagram", language: "ar", headline: null, body: "نص أول", call_to_action: null, hashtags: [], note: "Created", edited_by: null, created_at: new Date().toISOString() },
    ],
    fact_warnings: [], channel_limit: 2200, length: 40, ...over,
  };
}

describe("channel rules", () => {
  it("measures and validates content per channel", () => {
    expect(totalLength("Hi", "Body", null, ["#a", "#b"])).toBe("Hi\nBody\n#a #b".length);
    expect(parseHashtags("Riyadh #NewHome, #riyadh الرياض")).toEqual(["#Riyadh", "#NewHome", "#الرياض"]);
    expect(contentProblems("x", "", "a".repeat(281), "", [])).toHaveProperty("body");
    expect(contentProblems("email", "", "Hello", "", [])).toHaveProperty("headline");
    expect(contentProblems("email", "Subject", "Hello", "", ["#a"])).toHaveProperty("hashtags");
    expect(contentProblems("instagram", "", "Hello", "", ["#ok_1", "#الرياض"])).toEqual({});
  });

  it("previews Arabic content right-to-left", () => {
    render(<ContentPreview channel="x" language="ar" headline="" body="شقق جديدة" cta="" hashtags={["#الرياض"]} projectName="NOVA" />);
    const block = screen.getByText("شقق جديدة").closest("[lang]");
    expect(block).toHaveAttribute("lang", "ar");
    expect(block).toHaveAttribute("dir", "rtl");
    expect(screen.getByText(/\/ 280 characters · X/)).toBeInTheDocument();
  });
});

describe("content editor", () => {
  it("creates a draft manually while AI drafting is clearly unavailable", async () => {
    const calls = stubFetch({
      "/marketing/campaigns/c1": () => json(CAMPAIGN),
      "/marketing/projects/p1/facts": () => json(FACTS),
      "/marketing/ai-status": () => json(AI_OFF),
      "/marketing/facts-check": () => json([]),
      "/marketing/content": (init) => json(detail({ status: "draft", allowed_actions: ["edit", "submit", "archive"] }), init?.method === "POST" ? 201 : 200),
    });
    wrap("/marketing/content/new?campaign=c1");
    expect(await screen.findByText(/AI_MARKETING_STUDIO_ENABLED=false/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /draft with ai/i })).toBeDisabled();
    expect(await screen.findByText(/20 units/)).toBeInTheDocument(); // project facts panel
    await userEvent.type(screen.getByLabelText(/^Text/), "Homes from SAR 435,000.");
    await userEvent.type(screen.getByLabelText(/Hashtags/), "Riyadh NewHome");
    await userEvent.click(screen.getByRole("button", { name: /create draft/i }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/api/v1/marketing/content")).toBe(true));
    const post = calls.find((c) => c.method === "POST" && c.url === "/api/v1/marketing/content");
    expect(post?.body).toMatchObject({ campaign_id: "c1", channel: "instagram", language: "en", body: "Homes from SAR 435,000.", hashtags: ["#Riyadh", "#NewHome"] });
    expect(calls.some((c) => c.url.includes("/generate"))).toBe(false); // no AI call
  });

  it("locks content in review for its author and shows Arabic right-to-left", async () => {
    stubFetch({
      "/marketing/content/m1": () => json(detail()),
      "/marketing/campaigns/c1": () => json(CAMPAIGN),
      "/marketing/projects/p1/facts": () => json(FACTS),
      "/marketing/ai-status": () => json(AI_OFF),
    });
    wrap("/marketing/content/m1");
    expect(await screen.findByText(/editing is locked until a marketing manager decides/)).toHaveTextContent("You can't approve a request you submitted.");
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    const body = screen.getByLabelText(/^Text/);
    expect(body).toBeDisabled();
    expect(body).toHaveAttribute("dir", "rtl");
    expect(body).toHaveAttribute("lang", "ar");
    expect(screen.getByText("2 saved versions")).toBeInTheDocument();
  });

  it("lets an eligible manager approve through the approval engine", async () => {
    const calls = stubFetch({
      "/marketing/content/m1": () => json(detail({ can_decide: true, decide_blocked_reason: null, allowed_actions: ["approve", "reject"] })),
      "/marketing/campaigns/c1": () => json(CAMPAIGN),
      "/marketing/projects/p1/facts": () => json(FACTS),
      "/marketing/ai-status": () => json(AI_OFF),
      "/approvals/a1/approve": () => json({}),
      "/approvals/a1": () => json({ id: "a1", entity_type: "marketing_content", entity_label: "Marketing content", entity_id: "m1", entity_code: "MCT-00001",
        title: "Instagram content (AR)", amount: "0.00", status: "pending", flags: {}, requester: { id: "u1", full_name: "Lina" }, current_step: 1,
        current_step_label: "Marketing manager", waiting_on: null, link: "/marketing/content/m1", created_at: "", completed_at: null, can_decide: true,
        policy_name: "Marketing content review", allowed_actions: ["approve", "reject"], blocked_reason: null,
        steps: [{ step_order: 1, level: "marketing", label: "Marketing manager", status: "pending", assignee: null, pool_label: "Marketing approvers",
          escalation_reason: null, activated_at: null, decided_at: null, decision: null }] }),
    });
    wrap("/marketing/content/m1");
    await userEvent.click(await screen.findByRole("button", { name: /^approve$/i }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).not.toHaveTextContent("SAR"); // content has no amount
    expect(dialog).not.toHaveTextContent(/committed against the budget/);
    await userEvent.click(screen.getAllByRole("button", { name: /^approve$/i }).at(-1)!);
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/api/v1/approvals/a1/approve")).toBe(true));
  });
});
