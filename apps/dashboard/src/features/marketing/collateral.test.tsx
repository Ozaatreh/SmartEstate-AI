import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import CollateralPage from "./collateral-page";
import type { CollateralOptions } from "./collateral-api";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const OPTIONS: CollateralOptions = {
  facts: {
    project_id: "p1", code: "NOVA", name: "NOVA Residences", city: "Riyadh", district: "North Riyadh (fictional)", status: "launched",
    handover_date: "2028-12-31", description: null, is_demo_data: true, amenities: ["Swimming pool"], available_units: 20,
    price_from_sar: "435000.00", unit_types: [{ bedrooms: 0, available: 2, area_min_sqm: "46.00", area_max_sqm: "48.00", price_from_sar: "435000.00" }],
    payment_plans: [{ name: "10 / 90 over 3 years", down_payment_pct: "10.00", installments: 36, installment_frequency: "monthly", handover_pct: "0.00" }],
    excluded_plans: 1, images: [], contact: { phone: null, email: null, website: null }, as_of: new Date().toISOString(),
    missing: ["images", "description", "contact"],
  },
  key_facts: {
    en: [{ id: "available", label: "20 homes available" }, { id: "bedrooms", label: "Studio to 4 bedrooms" }, { id: "handover", label: "Handover Dec 2028" }, { id: "amenity:0", label: "Swimming pool" }],
    ar: [{ id: "available", label: "20 وحدة متاحة" }, { id: "bedrooms", label: "من استوديو إلى 4 غرف نوم" }, { id: "handover", label: "التسليم ديسمبر 2028" }, { id: "amenity:0", label: "Swimming pool" }],
  },
  sections: ["overview", "location", "amenities", "units", "prices", "payment_plans", "contact"].map((id) => ({ id, label: id })),
  formats: [
    { id: "instagram_post", label: "Instagram post", width: 1080, height: 1080 }, { id: "instagram_story", label: "Instagram story", width: 1080, height: 1920 },
    { id: "linkedin", label: "LinkedIn post", width: 1200, height: 627 }, { id: "facebook", label: "Facebook post", width: 1200, height: 630 },
  ],
  templates: [{ id: "classic", label: "Classic" }, { id: "split", label: "Split" }, { id: "minimal", label: "Minimal" }],
  ctas: { en: [{ id: "book_viewing", label: "Book a viewing" }], ar: [{ id: "book_viewing", label: "احجز موعد زيارة" }] },
};

function setup(initial = "/marketing/collateral") {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (url.endsWith("/marketing/collateral/projects")) return json([{ id: "p1", code: "NOVA", name: "NOVA Residences", is_demo_data: true }]);
    if (url.endsWith("/marketing/collateral/projects/p1")) return json(OPTIONS);
    if (url.endsWith("/preview")) return json({ html: '<html><body><section class="page">x</section></body></html>', width: 1080, height: 1080 });
    if (url.endsWith("/marketing/collateral/brochure")) {
      return new Response(new Blob(["%PDF-1.7"]), { headers: { "Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="NOVA-brochure-en.pdf"' } });
    }
    if (url.endsWith("/marketing/collateral/poster")) return new Response(new Blob(["png"]), { headers: { "Content-Disposition": 'attachment; filename="NOVA-linkedin-1200x627-ar.png"' } });
    return json({ error: { code: "not_found", message: "Not found" } }, 404);
  }));
  const created = vi.fn(() => "blob:x");
  URL.createObjectURL = created;
  URL.revokeObjectURL = vi.fn();
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[initial]}><CollateralPage /></MemoryRouter>
    </QueryClientProvider>,
  );
  return { calls, clicked };
}

describe("brochures & posters", () => {
  it("shows verified facts, what is missing, and downloads the brochure PDF", async () => {
    const { calls, clicked } = setup();
    expect(await screen.findByText("Verified facts")).toBeInTheDocument();
    expect(screen.getByText(/No approved project images — a neutral placeholder is used/)).toBeInTheDocument();
    expect(screen.getByText(/1 payment plan is left out because it isn't cleared for marketing/)).toBeInTheDocument();
    // sections without data can't be ticked
    const overview = screen.getByText("overview").closest("label")!;
    expect(within(overview).getByRole("checkbox")).toBeDisabled();
    expect(within(screen.getByText("units").closest("label")!).getByRole("checkbox")).toBeChecked();
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/brochure/preview"))).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: /download pdf/i }));
    await waitFor(() => expect(clicked).toHaveBeenCalled());
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/marketing/collateral/brochure"));
    expect(post?.body).toMatchObject({ project_id: "p1", language: "en", image_id: null });
    expect((post?.body as { sections: string[] }).sections).not.toContain("overview");
    expect(calls.some((c) => /generate|anthropic|\/ai\//.test(c.url))).toBe(false);
  });

  it("builds an Arabic LinkedIn poster from verified facts only", async () => {
    const { calls, clicked } = setup("/marketing/collateral?tab=poster");
    await screen.findByText("Verified facts");
    await userEvent.click(screen.getByRole("radio", { name: "العربية" }));
    await userEvent.click(screen.getByRole("radio", { name: /linkedin post/i }));
    expect(screen.getByText("1200 × 627 px", { exact: false })).toBeInTheDocument();
    // three facts are preselected; a fourth can't be added
    expect(within(screen.getByText("Swimming pool").closest("label")!).getByRole("checkbox")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /download png/i }));
    await waitFor(() => expect(clicked).toHaveBeenCalled());
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/marketing/collateral/poster"));
    expect(post?.body).toMatchObject({ project_id: "p1", language: "ar", format: "linkedin", show_price: true, facts: ["available", "bedrooms", "handover"] });
  });
});

describe("brochure-only image upload", () => {
  it("uploads a different image with its source and licence, then uses it for the cover", async () => {
    const uploaded = { id: "u1u1u1u1u1u1", caption: "Lobby", source: "Agency shoot", licence: "Print and social", origin: "upload" as const };
    let images: CollateralOptions["facts"]["images"] = [];
    const calls: { url: string; method: string; body: unknown }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body instanceof File ? init.body : init?.body ? JSON.parse(String(init.body)) : undefined });
      if (method === "PUT" && url.includes("/marketing/collateral/projects/p1/images")) { images = [uploaded]; return json(uploaded, 201); }
      if (url.endsWith("/marketing/collateral/projects")) return json([{ id: "p1", code: "NOVA", name: "NOVA Residences", is_demo_data: true }]);
      if (url.endsWith("/marketing/collateral/projects/p1")) return json({ ...OPTIONS, facts: { ...OPTIONS.facts, images } });
      if (url.endsWith("/preview")) return json({ html: '<html><body><section class="page">x</section></body></html>', width: 794, height: null });
      return json({ error: { code: "not_found", message: "Not found" } }, 404);
    }));
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/marketing/collateral"]}><CollateralPage /></MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: /upload a different image/i }));
    const form = screen.getByTestId("collateral-upload");
    await userEvent.upload(within(form).getByLabelText("Image file"), new File(["x"], "lobby.png", { type: "image/png" }));
    await userEvent.click(within(form).getByRole("button", { name: /^upload$/i }));
    expect(within(form).getByRole("alert")).toHaveTextContent("Record the image's source and licence.");
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    await userEvent.type(within(form).getByRole("textbox", { name: "Source" }), "Agency shoot");
    await userEvent.type(within(form).getByRole("textbox", { name: "Licence" }), "Print and social");
    await userEvent.type(within(form).getByRole("textbox", { name: "Caption (optional)" }), "Lobby");
    await userEvent.click(within(form).getByRole("button", { name: /^upload$/i }));
    await waitFor(() => expect(screen.queryByTestId("collateral-upload")).not.toBeInTheDocument());
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.url).toContain("source=Agency+shoot");
    expect(put.url).toContain("licence=Print+and+social");
    expect(put.body).toBeInstanceOf(File);
    expect(await screen.findByRole("combobox", { name: "Image" })).toHaveTextContent("Lobby · brochure only");
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/brochure/preview") && (c.body as { image_id: string }).image_id === uploaded.id)).toBe(true));
  });
});
