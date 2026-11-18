import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import AssistantPage from "@/features/assistant/assistant-page";
import { InquiryForm } from "@/features/inquiry/inquiry-form";
import { validate, type Values } from "@/features/inquiry/validation";
import { parseSseChunk, publicUrl } from "@/lib/api";
import { ProjectPage, ProjectsPage } from "@/pages/projects";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const sse = (...events: object[]) => new Response(events.map((e) => `event: ${(e as { type: string }).type}\ndata: ${JSON.stringify(e)}\n\n`).join(""),
  { status: 200, headers: { "Content-Type": "text/event-stream" } });

function stubFetch(routes: Record<string, () => Response>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const key = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => url.includes(k));
    return key ? routes[key]!() : json({ error: { code: "not_found", message: "Not found" } }, 404);
  }));
  return calls;
}

const wrap = (ui: React.ReactNode, path = "/") => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
  </QueryClientProvider>,
);

const PROJECT = { code: "NOVA", name: "NOVA Residences", city: "Riyadh", district: "Al Malqa", status: "launched", handover_date: "2028-06-30",
  is_demo_data: true, available_units: 2, price_from_sar: "650000.00", cover_image: null };

describe("public API client", () => {
  it("only builds /api/v1/public URLs", () => {
    expect(publicUrl("/projects", { bedrooms: 2, q: null })).toBe("/api/v1/public/projects?bedrooms=2");
    expect(() => publicUrl("../crm/leads")).toThrow();
    expect(() => publicUrl("/../../crm/leads")).toThrow();
    expect(() => publicUrl("//evil.example/x")).toThrow();
  });

  it("parses server-sent events across chunks", () => {
    const a = parseSseChunk('event: text\ndata: {"type":"text","text":"Hi"}\n\nevent: do');
    expect(a.events).toEqual([{ type: "text", text: "Hi" }]);
    expect(parseSseChunk(a.rest + 'ne\ndata: {"type":"done"}\n\n').events).toEqual([{ type: "done" }]);
  });
});

describe("inquiry form", () => {
  const base: Values = { full_name: "Rana", email: "", phone: "", message: "", project_code: "", unit_code: "", preferred_date: "",
    preferred_language: "en", consent: false, website: "" };

  it("validates before sending (the server validates again)", () => {
    expect(validate("contact", base)).toMatchObject({ contact: expect.any(String), message: expect.any(String), consent: expect.any(String) });
    expect(validate("contact", { ...base, phone: "abc" }).phone).toBeTruthy();
    expect(validate("viewing", { ...base, phone: "+966 50 123 4567", consent: true, preferred_date: "2001-01-01" }))
      .toMatchObject({ project_code: expect.any(String), preferred_date: expect.any(String) });
    expect(validate("contact", { ...base, email: "r@example.com", message: "Hi", consent: true })).toEqual({});
  });

  it("sends the form with its token and a hidden honeypot, then confirms", async () => {
    const calls = stubFetch({
      "/inquiries/form-token": () => json({ token: "1700000000.abc", min_fill_seconds: 3 }),
      "/inquiries": () => json({ status: "received", message: "Thank you — our sales team will contact you shortly." }, 202),
    });
    wrap(<InquiryForm kind="contact" />);
    await userEvent.type(screen.getByLabelText(/full name/i), "Rana Fictional");
    await userEvent.type(screen.getByLabelText(/e-mail/i), "rana@example.com");
    await userEvent.type(screen.getByLabelText(/^message/i), "Interested in NOVA");
    await userEvent.click(screen.getByRole("checkbox"));
    const honeypot = document.getElementById("q-website") as HTMLInputElement;
    expect(honeypot.closest("[aria-hidden='true']")).not.toBeNull();
    expect(honeypot.tabIndex).toBe(-1);
    await waitFor(() => expect(screen.getByRole("button", { name: /send message/i })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));
    expect(await screen.findByRole("status")).toHaveTextContent("Request received");
    const post = calls.find((c) => c.method === "POST");
    expect(post).toMatchObject({ url: "/api/v1/public/inquiries", body: { kind: "contact", full_name: "Rana Fictional", email: "rana@example.com",
      phone: null, consent: true, website: "", form_token: "1700000000.abc" } });
  });

  it("shows the server's field and rate-limit errors", async () => {
    let n = 0;
    stubFetch({
      "/inquiries/form-token": () => json({ token: "1700000000.abc" }),
      "/inquiries": () => (++n === 1
        ? json({ error: { code: "validation_failed", message: "Some fields are invalid.", details: { fields: [{ field: "phone", message: "Enter a valid phone number." }] } } }, 422)
        : json({ error: { code: "inquiry_rate_limited", message: "Too many requests from your network. Please try again later." } }, 429)),
    });
    wrap(<InquiryForm kind="contact" />);
    await userEvent.type(screen.getByLabelText(/full name/i), "Rana");
    await userEvent.type(screen.getByLabelText(/phone/i), "+966 50 123 4567");
    await userEvent.type(screen.getByLabelText(/^message/i), "Hi");
    await userEvent.click(screen.getByRole("checkbox"));
    await waitFor(() => expect(screen.getByRole("button", { name: /send message/i })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));
    expect(await screen.findByText("Enter a valid phone number.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many requests");
  });
});

describe("listings", () => {
  it("lists published projects", async () => {
    stubFetch({ "/projects": () => json([PROJECT]) });
    wrap(<ProjectsPage />);
    expect(await screen.findByRole("link", { name: /NOVA Residences/ })).toHaveAttribute("href", "/projects/NOVA");
    expect(screen.getByText("Starting from").nextElementSibling).toHaveTextContent("SAR 650,000");
    expect(screen.getAllByText(/Fictional/i).length).toBeGreaterThan(0);
  });

  it("shows a friendly not-found page for unknown or unpublished projects", async () => {
    stubFetch({});
    wrap(<Routes><Route path="/projects/:code" element={<ProjectPage />} /></Routes>, "/projects/HIDDEN");
    expect(await screen.findByRole("heading", { name: "We couldn't find that project" })).toBeInTheDocument();
  });
});

describe("property assistant (moved from the dashboard)", () => {
  it("shows unit cards and sends the visitor's consent with the message", async () => {
    const calls = stubFetch({
      "/assistant/status": () => json({ available: true, message: "ok" }),
      "/assistant/messages": () => sse(
        { type: "start", conversation_id: "v1" },
        { type: "tool", name: "search_units", label: "Searched available units", status: "ok", summary: "1 available units found", cards: [{
          kind: "units", units: [{ code: "A-102", project: "NOVA Residences", project_code: "NOVA", type: "apartment", bedrooms: 2, bathrooms: 2,
            floor: 1, area_sqm: "110.00", view: null, list_price_sar: "900000.00", status: "available" }] }] },
        { type: "text", text: "A-102 fits your budget." },
        { type: "done", conversation_id: "v1", truncated: false, tools: [] },
      ),
    });
    wrap(<AssistantPage />);
    expect(await screen.findByRole("note")).toHaveTextContent("Fictional Demo Data");
    await waitFor(() => expect(screen.getByRole("checkbox")).toBeEnabled());
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.type(screen.getByLabelText("Message"), "2 bedrooms under 1M{Enter}");
    expect(await screen.findByText("A-102 fits your budget.")).toBeInTheDocument();
    expect(screen.getByText("SAR 900,000")).toBeInTheDocument();
    expect(screen.getAllByText("AI-generated").length).toBeGreaterThan(0);
    const post = calls.find((c) => c.method === "POST");
    expect(post).toMatchObject({ url: "/api/v1/public/assistant/messages", body: { conversation_id: null, message: "2 bedrooms under 1M", contact_consent: true } });
  });

  it("explains when the assistant is unavailable", async () => {
    stubFetch({ "/assistant/status": () => json({ available: false, message: "x" }) });
    wrap(<AssistantPage />);
    expect(await screen.findByRole("status")).toHaveTextContent("not available right now");
    expect(screen.getByLabelText("Message")).toBeDisabled();
  });
});

describe("theme", () => {
  it("toggles light/dark, remembers the choice and follows the system on first visit", async () => {
    const { ThemeToggle } = await import("@/components/layout");
    localStorage.removeItem("smartestate-theme");
    document.documentElement.classList.remove("dark");
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: "Switch to dark theme" }); // jsdom's system preference is light
    await userEvent.click(button);
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("smartestate-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to light theme" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem("smartestate-theme")).toBe("light");
  });
});

describe("language", () => {
  it("shows the site in Arabic, right-to-left, with Arabic labels, prices and validation", async () => {
    const { I18nProvider } = await import("@/lib/i18n");
    stubFetch({ "/projects": () => json([PROJECT]), "/inquiries/form-token": () => json({ token: "t" }) });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider initial="ar"><MemoryRouter><ProjectsPage /><InquiryForm kind="contact" /></MemoryRouter></I18nProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: "مجتمعات متاحة للبيع" })).toBeInTheDocument();
    await waitFor(() => expect(document.documentElement).toHaveAttribute("dir", "rtl"));
    expect(document.documentElement).toHaveAttribute("lang", "ar");
    expect(screen.getByText("تبدأ من").nextElementSibling).toHaveTextContent("650,000 ر.س");
    expect(screen.getByText("مُطلق")).toBeInTheDocument(); // status "launched"
    await waitFor(() => expect(screen.getByRole("button", { name: "إرسال الرسالة" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "إرسال الرسالة" }));
    expect(await screen.findByText("أدخل اسمك.")).toBeInTheDocument();
    expect(screen.getByLabelText("اللغة المفضّلة")).toHaveValue("ar");
  });

  it("switches language from the header and remembers the choice", async () => {
    const { I18nProvider, applyLang } = await import("@/lib/i18n");
    const { LanguageSwitch } = await import("@/components/layout");
    applyLang("en");
    localStorage.removeItem("smartestate-lang");
    render(<I18nProvider initial="en"><LanguageSwitch /></I18nProvider>);
    await userEvent.click(screen.getByRole("button", { name: "التبديل إلى العربية" }));
    expect(localStorage.getItem("smartestate-lang")).toBe("ar");
    await waitFor(() => expect(document.documentElement).toHaveAttribute("dir", "rtl"));
    await userEvent.click(screen.getByRole("button", { name: "Switch to English" }));
    await waitFor(() => expect(document.documentElement).toHaveAttribute("dir", "ltr"));
    expect(localStorage.getItem("smartestate-lang")).toBe("en");
  });
});

describe("motion", () => {
  it("reveals content once on scroll, and immediately when the visitor prefers reduced motion", async () => {
    const { Reveal } = await import("@/components/motion");
    let fire: (visible: boolean) => void = () => undefined;
    const observe = vi.fn();
    const disconnect = vi.fn();
    vi.stubGlobal("IntersectionObserver", class {
      constructor(cb: (entries: { isIntersecting: boolean }[]) => void) { fire = (v) => cb([{ isIntersecting: v }]); }
      observe = observe; disconnect = disconnect; unobserve() {}
    });
    const { unmount } = render(<Reveal data-testid="r">Section</Reveal>);
    const el = screen.getByTestId("r");
    expect(el).toHaveClass("reveal");
    expect(el).not.toHaveClass("is-visible");
    await import("@testing-library/react").then(({ act }) => act(() => fire(true)));
    expect(el).toHaveClass("is-visible");
    expect(disconnect).toHaveBeenCalled(); // never replays
    unmount();

    vi.spyOn(window, "matchMedia").mockImplementation((q: string) => ({ matches: q.includes("reduce"), media: q, onchange: null,
      addEventListener: () => undefined, removeEventListener: () => undefined, addListener: () => undefined, removeListener: () => undefined, dispatchEvent: () => false }));
    render(<Reveal data-testid="r2">Section</Reveal>);
    expect(screen.getByTestId("r2")).toHaveClass("is-visible");
  });
});
