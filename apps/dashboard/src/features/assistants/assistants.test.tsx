import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseSseChunk } from "@/lib/api-client";
import { applyEvent, columnLabel, type ChatMessage } from "./api";
import BIAgentPage from "./bi-agent-page";
import { RichText } from "./chat";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const sse = (...events: object[]) => events.map((e) => `event: ${(e as { type: string }).type}\ndata: ${JSON.stringify(e)}\n\n`).join("");
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const stream = (body: string) => new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });

/** Routes fetch by URL; records POST bodies. */
function stubFetch(routes: Record<string, () => Response>) {
  const posts: { url: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") posts.push({ url, body: JSON.parse(String(init.body)) });
    const key = Object.keys(routes).find((k) => url.includes(k));
    return key ? routes[key]!() : json({ error: { code: "not_found", message: "Not found" } }, 404);
  }));
  return posts;
}

const wrap = (ui: React.ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>,
);

describe("streaming helpers", () => {
  it("parses server-sent events across chunk boundaries", () => {
    const full = sse({ type: "start", conversation_id: "c1" }, { type: "text", text: "Hel" });
    const a = parseSseChunk(full.slice(0, 30));
    expect(a.events).toEqual([]);
    const b = parseSseChunk(a.rest + full.slice(30));
    expect(b.events).toEqual([{ type: "start", conversation_id: "c1" }, { type: "text", text: "Hel" }]);
    expect(b.rest).toBe("");
  });

  it("builds the assistant message from events", () => {
    let m: ChatMessage = { id: "a", role: "assistant", text: "", tools: [], cards: [], status: "streaming" };
    m = applyEvent(m, { type: "text", text: "FIN is " });
    m = applyEvent(m, { type: "tool", name: "get_budget_positions", label: "Checked budget positions", status: "ok", summary: "FY2026", cards: [{ kind: "lead_created" }] });
    m = applyEvent(m, { type: "text", text: "closest." });
    m = applyEvent(m, { type: "done", truncated: false });
    expect(m).toMatchObject({ text: "FIN is closest.", status: "done", cards: [{ kind: "lead_created" }] });
    expect(m.tools[0]).toMatchObject({ label: "Checked budget positions", status: "ok" });
    expect(applyEvent(m, { type: "error", message: "Busy" })).toMatchObject({ status: "error", error: "Busy" });
  });

  it("labels table columns with their units", () => {
    expect(columnLabel("allocated_sar")).toBe("Allocated (SAR)");
    expect(columnLabel("utilisation_pct")).toBe("Utilisation (%)");
    expect(columnLabel("department")).toBe("Department");
  });

  it("renders a safe Markdown subset and never injects HTML", () => {
    const { container } = render(<RichText text={"**Top:** FIN\n\n- one\n- two\n\n| Dept | % |\n|---|---|\n| FIN | 90 |\n\n<img src=x onerror=alert(1)>"} />);
    expect(container.querySelector("strong")).toHaveTextContent("Top:");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(within(container.querySelector("table")!).getByText("90")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container).toHaveTextContent("<img src=x onerror=alert(1)>");
  });
});

describe("BI agent page", () => {
  it("streams an answer with the tools it used", async () => {
    const posts = stubFetch({
      "/ai/status": () => json({ state: "operational", reason: "ok", usable: true }),
      "/ai/bi/conversations": () => json([]),
      "/ai/bi/messages": () => stream(sse(
        { type: "start", conversation_id: "c1" },
        { type: "tool", name: "get_budget_positions", label: "Checked budget positions", status: "ok", summary: "FY2026 · 5 departments", cards: null },
        { type: "tool", name: "get_lead_funnel", label: "Checked the lead funnel", status: "denied", summary: "Permission denied.", cards: null },
        { type: "text", text: "The **FIN** department is closest (90%)." },
        { type: "done", conversation_id: "c1", truncated: false, tools: [] },
      )),
    });
    wrap(<BIAgentPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Which department is closest to its budget limit?" }));
    expect(await screen.findByText((_, el) => el?.tagName === "P" && el.textContent === "The FIN department is closest (90%).")).toBeInTheDocument();
    const used = screen.getByRole("list", { name: "Data used" });
    expect(used).toHaveTextContent("Checked budget positions · FY2026 · 5 departments");
    expect(used).toHaveTextContent("(denied)");
    expect(screen.getAllByText("AI-generated").length).toBeGreaterThan(0);
    expect(posts[0]).toEqual({ url: "/api/v1/ai/bi/messages", body: { conversation_id: null, message: "Which department is closest to its budget limit?" } });
  });

  it("shows the unavailable state and disables the composer when AI is off", async () => {
    stubFetch({
      "/ai/status": () => json({ state: "disabled", reason: "AI features are turned off (AI_ENABLED=false).", usable: false }),
      "/ai/bi/conversations": () => json([]),
    });
    wrap(<BIAgentPage />);
    expect(await screen.findByRole("status")).toHaveTextContent(/unavailable right now.*work as usual/);
    expect(screen.getByLabelText("Message")).toBeDisabled();
  });

  it("reports a refused request (e.g. 503) inline", async () => {
    stubFetch({
      "/ai/status": () => json({ state: "unverified", reason: "ok", usable: true }),
      "/ai/bi/conversations": () => json([]),
      "/ai/bi/messages": () => json({ error: { code: "ai_budget_exceeded", message: "The daily AI budget has been reached. Try again tomorrow." } }, 503),
    });
    wrap(<BIAgentPage />);
    await userEvent.type(await screen.findByLabelText("Message"), "Budget?{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("daily AI budget");
  });
});
