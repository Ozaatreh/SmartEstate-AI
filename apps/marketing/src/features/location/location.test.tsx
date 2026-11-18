import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectCover } from "@/components/listing";
import type { PublicLocation } from "@/lib/api";
import { findPanorama } from "./maps";
import { ProjectLocation } from "./project-location";

const mocks = vi.hoisted(() => ({ load: vi.fn(), authFail: null as null | (() => void) }));
vi.mock("./maps", async (orig) => ({
  ...(await orig<typeof import("./maps")>()),
  loadMapsApi: mocks.load,
  onMapsAuthFailure: (f: () => void) => { mocks.authFail = f; return () => { mocks.authFail = null; }; },
}));

// Minimal stand-in for google.maps (the real API is checked in the browser).
const g = {
  Map: vi.fn(), Marker: vi.fn(), Panorama: vi.fn(),
  getPanorama: vi.fn(),
};
beforeEach(() => {
  mocks.load.mockResolvedValue(undefined);
  g.getPanorama.mockResolvedValue({ data: { location: { pano: "PANO_1" } } });
  vi.stubGlobal("google", {
    maps: {
      importLibrary: vi.fn(async (name: string) => ({
        maps: { Map: g.Map },
        marker: { AdvancedMarkerElement: g.Marker },
        streetView: {
          StreetViewService: class { getPanorama = g.getPanorama; },
          StreetViewPanorama: g.Panorama,
        },
      })[name]),
    },
  });
});
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

const VERIFIED: PublicLocation = {
  district: "Al Malqa", city: "Riyadh", country: "Saudi Arabia", address: "King Salman Rd", latitude: "24.812345", longitude: "46.612345",
  verified: true, directions_url: "https://www.google.com/maps/dir/?api=1&destination=24.812345%2C46.612345",
  maps_url: "https://www.google.com/maps/search/?api=1&query=24.812345%2C46.612345",
};
const UNVERIFIED: PublicLocation = {
  district: "North Riyadh (fictional)", city: "Riyadh", country: null, address: null, latitude: null, longitude: null,
  verified: false, directions_url: null, maps_url: null,
};

const show = (location: PublicLocation, props: Partial<React.ComponentProps<typeof ProjectLocation>> = {}) =>
  render(<MemoryRouter><ProjectLocation location={location} projectName="Real Court" projectCode="REAL" isDemo={false} apiKey=""
    mapId="TEST_MAP" streetView {...props} /></MemoryRouter>);

describe("project location — map mode (Maps JavaScript API)", () => {
  it("draws an interactive map with a pin on the verified point, plus directions links", async () => {
    show(VERIFIED, { apiKey: "test-browser-key", lang: "en" });
    await waitFor(() => expect(g.Map).toHaveBeenCalled());
    expect(mocks.load).toHaveBeenCalledWith("test-browser-key", "en");
    const [el, opts] = g.Map.mock.calls[0] as [HTMLElement, google.maps.MapOptions];
    expect(el).toBe(screen.getByRole("region", { name: "Interactive map of Real Court" }));
    expect(opts).toMatchObject({ center: { lat: 24.812345, lng: 46.612345 }, zoom: 16, mapId: "TEST_MAP" });
    expect(g.Marker).toHaveBeenCalledWith(expect.objectContaining({ position: { lat: 24.812345, lng: 46.612345 }, title: "Real Court" }));
    expect(screen.getByRole("tab", { name: "Map" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: /get directions/i })).toHaveAttribute("href", VERIFIED.directions_url);
    expect(screen.getByRole("link", { name: /open in google maps/i })).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText("King Salman Rd")).toBeInTheDocument();
  });

  it("falls back to text and links when no key is configured", () => {
    show(VERIFIED);
    expect(mocks.load).not.toHaveBeenCalled();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.getByTestId("map-nokey")).toHaveTextContent(/interactive map isn't available/i);
    expect(screen.getByRole("link", { name: /get directions/i })).toBeInTheDocument();
  });

  it("shows a clean error, keeping the links, when Google can't load or rejects the key", async () => {
    mocks.load.mockRejectedValueOnce(new Error("maps_load_failed"));
    show(VERIFIED, { apiKey: "k" });
    expect(await screen.findByTestId("map-error")).toHaveTextContent(/couldn't be loaded/);
    expect(screen.getByRole("link", { name: /get directions/i })).toBeInTheDocument();
  });

  it("switches to the error state when Google rejects the key after loading", async () => {
    show(VERIFIED, { apiKey: "k" });
    await waitFor(() => expect(g.Map).toHaveBeenCalled());
    expect(mocks.authFail).not.toBeNull();
    act(() => mocks.authFail!());
    expect(await screen.findByTestId("map-error")).toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  });
});

describe("project location — Street View", () => {
  it("opens Google's Street View panorama inside the page", async () => {
    show(VERIFIED, { apiKey: "k" });
    await waitFor(() => expect(g.Map).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("tab", { name: "Street View" }));
    await waitFor(() => expect(g.Panorama).toHaveBeenCalled());
    const [el, opts] = g.Panorama.mock.calls[0] as [HTMLElement, google.maps.StreetViewPanoramaOptions];
    expect(el).toBe(screen.getByRole("region", { name: "Street View near Real Court" }));
    expect(opts.pano).toBe("PANO_1");
    expect(g.getPanorama).toHaveBeenCalledWith({ location: { lat: 24.812345, lng: 46.612345 }, radius: 50, sources: ["google"] });
    // switching back and forth doesn't look it up again
    await userEvent.click(screen.getByRole("tab", { name: "Map" }));
    await userEvent.click(screen.getByRole("tab", { name: "Street View" }));
    expect(g.getPanorama).toHaveBeenCalledTimes(1);
  });

  it("shows a clean fallback when there is no Google imagery near the point", async () => {
    g.getPanorama.mockRejectedValueOnce(Object.assign(new Error("none"), { code: "ZERO_RESULTS" }));
    show(VERIFIED, { apiKey: "k" });
    await waitFor(() => expect(g.Map).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("tab", { name: "Street View" }));
    expect(await screen.findByTestId("streetview-unavailable")).toHaveTextContent("Street View imagery isn't available at this location.");
    expect(g.Panorama).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /back to the map/i }));
    expect(screen.getByRole("tab", { name: "Map" })).toHaveAttribute("aria-selected", "true");
  });

  it("explains that Street View isn't available when it isn't enabled for the key (e.g. Maps Demo Key)", async () => {
    show(VERIFIED, { apiKey: "k", streetView: false });
    await waitFor(() => expect(g.Map).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("tab", { name: "Street View" }));
    expect(screen.getByTestId("streetview-off")).toHaveTextContent("Street View isn't available on this website yet.");
    expect(g.getPanorama).not.toHaveBeenCalled();
    expect(g.Panorama).not.toHaveBeenCalled();
  });

  it("classifies panorama lookups", async () => {
    const svc = (impl: () => Promise<unknown>) => ({ getPanorama: vi.fn(impl) }) as unknown as google.maps.StreetViewService;
    expect(await findPanorama(svc(async () => ({ data: { location: { pano: "p" } } })), 1, 2)).toEqual({ status: "available", pano: "p" });
    expect(await findPanorama(svc(async () => ({ data: {} })), 1, 2)).toEqual({ status: "unavailable" });
    expect(await findPanorama(svc(async () => { throw Object.assign(new Error(), { code: "ZERO_RESULTS" }); }), 1, 2)).toEqual({ status: "unavailable" });
    expect(await findPanorama(svc(async () => { throw new Error("network"); }), 1, 2)).toEqual({ status: "unknown" });
  });
});

describe("project location — privacy and verification", () => {
  it("never loads Google, or shows a map, Street View, pin or directions, without verified coordinates", () => {
    show(UNVERIFIED, { apiKey: "test-browser-key", isDemo: true });
    expect(mocks.load).not.toHaveBeenCalled();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /directions|google maps/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("map-fallback")).toHaveTextContent(/fictional demo project, so it has no real address and no map pin/);
    expect(screen.getByText("North Riyadh (fictional), Riyadh")).toBeInTheDocument();
  });

  it("ignores coordinates sent with an unverified location", () => {
    show({ ...UNVERIFIED, latitude: "24.757204", longitude: "46.631072" }, { apiKey: "k", isDemo: true });
    expect(mocks.load).not.toHaveBeenCalled();
    expect(screen.queryByText(/24\.757204/)).not.toBeInTheDocument();
  });

  it("asks visitors to contact the team when a real project's location isn't published", () => {
    show(UNVERIFIED);
    expect(screen.getByRole("link", { name: /ask for directions/i })).toHaveAttribute("href", "/request-viewing?project=REAL");
  });

  it("renders Arabic right-to-left and loads Google in Arabic", async () => {
    show(VERIFIED, { lang: "ar", apiKey: "k" });
    expect(screen.getByRole("region", { name: "الموقع" })).toHaveAttribute("dir", "rtl");
    expect(screen.getByRole("tab", { name: "التجوّل الافتراضي" })).toBeInTheDocument();
    await waitFor(() => expect(mocks.load).toHaveBeenCalledWith("k", "ar"));
  });

  it("ignores links that don't point to Google Maps and coordinates out of range", () => {
    show({ ...VERIFIED, directions_url: "https://evil.example/x", maps_url: "javascript:alert(1)" }, { apiKey: "k" });
    expect(screen.queryByRole("link", { name: /directions|google maps/i })).not.toBeInTheDocument();
    show({ ...VERIFIED, latitude: "123" }, { apiKey: "k" });
    expect(screen.getAllByTestId("map-fallback")).toHaveLength(1);
  });
});

describe("project location — illustrative reference point", () => {
  const ILL: PublicLocation = {
    ...UNVERIFIED, country: "Saudi Arabia",
    illustrative: {
      label: "Kingdom Centre, Riyadh", latitude: "24.711389", longitude: "46.674439",
      notice: "Illustrative Location — Not the Actual Property Location.",
      directions_url: "https://www.google.com/maps/dir/?api=1&destination=24.711389%2C46.674439",
      maps_url: "https://www.google.com/maps/search/?api=1&query=24.711389%2C46.674439",
    },
  };

  it("shows a pinned map clearly labelled as illustrative, with directions to the reference point only", async () => {
    show(ILL, { apiKey: "k", isDemo: true });
    expect(screen.getByTestId("illustrative-notice")).toHaveTextContent("Illustrative Location — Not the Actual Property Location.");
    expect(screen.getByTestId("illustrative-notice")).toHaveTextContent(/fictional demo project with no real address.*Kingdom Centre, Riyadh, a reference point/);
    expect(screen.getByTestId("map-badge")).toHaveTextContent("Illustrative location");
    await waitFor(() => expect(g.Map).toHaveBeenCalled());
    expect((g.Map.mock.calls[0] as [HTMLElement, google.maps.MapOptions])[1].center).toEqual({ lat: 24.711389, lng: 46.674439 });
    expect(g.Marker).toHaveBeenCalledWith(expect.objectContaining({ title: "Kingdom Centre, Riyadh (illustrative reference point)" }));
    expect(screen.getByRole("link", { name: "Directions to Kingdom Centre, Riyadh (reference point)" })).toHaveAttribute("href", ILL.illustrative!.directions_url);
    expect(screen.getByRole("link", { name: "Open Kingdom Centre, Riyadh in Google Maps" })).toBeInTheDocument();
    // never presented as the property's own address or directions
    expect(screen.queryByRole("link", { name: /^get directions$/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId("map-fallback")).not.toBeInTheDocument();
    expect(screen.getByText("North Riyadh (fictional), Riyadh, Saudi Arabia")).toBeInTheDocument();
  });

  it("keeps the label and links without a key, and shows it in Arabic", () => {
    show(ILL, { isDemo: true, lang: "ar" });
    expect(mocks.load).not.toHaveBeenCalled();
    expect(screen.getByTestId("illustrative-notice")).toHaveTextContent("موقع توضيحي — ليس الموقع الفعلي للعقار.");
    expect(screen.getByTestId("map-nokey")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /الاتجاهات إلى Kingdom Centre, Riyadh \(نقطة مرجعية\)/ })).toBeInTheDocument();
  });

  it("is ignored when the location is verified, and when the data is malformed", () => {
    show({ ...VERIFIED, illustrative: ILL.illustrative }, { apiKey: "" });
    expect(screen.queryByTestId("illustrative-notice")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /get directions/i })).toHaveAttribute("href", VERIFIED.directions_url);
    show({ ...ILL, illustrative: { ...ILL.illustrative!, latitude: "999", directions_url: "https://evil.example" } }, { apiKey: "k", isDemo: true });
    expect(screen.getAllByTestId("map-fallback")).toHaveLength(1);
  });
});

describe("project cover image", () => {
  it("shows the image, and the branded panel if it fails to load (no broken-image icon)", () => {
    render(<ProjectCover project={{ name: "Tower", cover_image: "https://cdn.example/tower.jpg" }} note />);
    const img = screen.getByRole("img", { name: "Tower" });
    fireEvent.error(img);
    expect(screen.getByTestId("cover-placeholder")).toHaveAccessibleName("Tower — images coming soon");
  });

  it("uses the panel when there is no valid image", () => {
    render(<ProjectCover project={{ name: "NOVA", cover_image: null }} note />);
    expect(screen.getByText("Project images coming soon")).toBeInTheDocument();
  });
});
