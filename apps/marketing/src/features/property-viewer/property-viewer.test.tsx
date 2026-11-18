import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PropertySceneProps } from "./property-scene";
import { Explore3DSection } from "./explore-3d-section";
import { InteractivePropertyViewer } from "./interactive-property-viewer";
import { SHOWCASES, VILLA_CAMERA } from "./showcases";

const webgl = vi.hoisted(() => ({ ok: true }));
vi.mock("@/features/model-viewer/webgl", () => ({ hasWebGL: () => webgl.ok }));

/** Stand-in for the three.js scene: "loads" (or fails) according to `scene.mode`. */
const scene = vi.hoisted(() => ({ mode: "load" as "load" | "fail" | "pending", reset: vi.fn(), urls: [] as string[] }));
vi.mock("./property-scene", () => ({
  default: function FakeScene({ url, label, handle, onLoaded, onProgress }: PropertySceneProps) {
    scene.urls.push(url);
    React.useImperativeHandle(handle, () => ({ reset: scene.reset }));
    React.useEffect(() => {
      if (scene.mode === "load") { onProgress(100); onLoaded(); } else if (scene.mode === "pending") onProgress(42);
    }, [onLoaded, onProgress]);
    if (scene.mode === "fail") throw new Error("GLB failed");
    return <div data-testid="scene" aria-label={label} />;
  },
}));
vi.mock("@react-three/drei", () => ({ useGLTF: { clear: vi.fn() } }));

const NOVA = SHOWCASES.NOVA!;
const viewer = () => render(<InteractivePropertyViewer modelUrl={NOVA.modelUrl} posterUrl={NOVA.posterUrl} title="NOVA Residences" camera={VILLA_CAMERA} />);

beforeEach(() => { webgl.ok = true; scene.mode = "load"; scene.reset.mockClear(); scene.urls = []; });
afterEach(() => vi.restoreAllMocks());

describe("InteractivePropertyViewer", () => {
  it("loads the static GLB and shows the instruction, reset and fullscreen controls", async () => {
    viewer();
    expect(await screen.findByTestId("scene")).toHaveAccessibleName(/Interactive 3D model: NOVA Residences/);
    expect(scene.urls).toContain("/models/smartestate_modern_villa.glb");
    expect(await screen.findByRole("button", { name: "Reset camera" })).toBeInTheDocument();
    expect(screen.getByTestId("property-viewer")).toHaveAttribute("data-status", "ready");
    expect(screen.getByTestId("viewer-hint")).toHaveTextContent("Drag to rotate · Scroll to zoom");
    await userEvent.click(screen.getByRole("button", { name: "Reset camera" }));
    expect(scene.reset).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Fullscreen" })).toBeInTheDocument();
  });

  it("shows a loading indicator with progress until the model is ready", async () => {
    scene.mode = "pending";
    viewer();
    expect(await screen.findByRole("status")).toHaveTextContent("Loading 3D model · 42%");
    expect(screen.queryByRole("button", { name: "Reset camera" })).not.toBeInTheDocument();
  });

  it("reports a load error and retries", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined); // React logs the caught error
    scene.mode = "fail";
    viewer();
    expect(await screen.findByRole("alert")).toHaveTextContent("The 3D model couldn't be loaded.");
    scene.mode = "load";
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: "Reset camera" })).toBeInTheDocument();
    expect(screen.getByTestId("property-viewer")).toHaveAttribute("data-status", "ready");
  });

  it("falls back to a still image when WebGL isn't available, without loading three.js", () => {
    webgl.ok = false;
    viewer();
    expect(screen.getByTestId("viewer-unsupported")).toHaveTextContent("Interactive 3D isn't available on this device.");
    expect(screen.getByRole("img", { name: "Still image of the 3D model: NOVA Residences" })).toHaveAttribute("src", NOVA.posterUrl);
    expect(scene.urls).toEqual([]);
  });

  it("uses the Fullscreen API, and a full-window overlay where it isn't supported (closed with Escape)", async () => {
    const request = vi.fn(() => Promise.resolve());
    Object.defineProperty(HTMLElement.prototype, "requestFullscreen", { value: request, configurable: true });
    const { unmount } = viewer();
    await userEvent.click(await screen.findByRole("button", { name: "Fullscreen" }));
    expect(request).toHaveBeenCalledOnce();
    unmount();

    // @ts-expect-error -- simulate a browser without element fullscreen (e.g. iPhone Safari)
    delete HTMLElement.prototype.requestFullscreen;
    viewer();
    await userEvent.click(await screen.findByRole("button", { name: "Fullscreen" }));
    expect(screen.getByTestId("property-viewer").className).toContain("fixed");
    expect(screen.getByRole("button", { name: "Exit fullscreen" })).toBeInTheDocument();
    act(() => { fireEvent.keyDown(window, { key: "Escape" }); });
    expect(screen.getByTestId("property-viewer").className).not.toContain("fixed");
  });
});

describe("Explore in 3D section", () => {
  const links = [
    { label: "Project overview", href: "#overview" }, { label: "Amenities", href: "#amenities" },
    { label: "Available units", href: "#units" }, { label: "Request information", href: "/request-viewing?project=NOVA" },
  ];

  it("presents the viewer with its copy, the illustrative-model notice and the page links", async () => {
    render(<MemoryRouter><Explore3DSection projectName="NOVA Residences" showcase={NOVA} links={links} /></MemoryRouter>);
    expect(screen.getByText("Explore in 3D")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Experience NOVA from Every Angle." })).toBeInTheDocument();
    expect(screen.getByText(/interactive 360-degree experience/)).toBeInTheDocument();
    expect(screen.getByTestId("explore-3d-notice")).toHaveTextContent("not the actual design of NOVA Residences");
    expect(await screen.findByTestId("scene")).toBeInTheDocument();
    for (const l of links) expect(screen.getByRole("link", { name: l.label })).toHaveAttribute("href", l.href);
  });

  it("is configured only for NOVA, with a static model file", () => {
    expect(Object.keys(SHOWCASES)).toEqual(["NOVA"]);
    expect(NOVA.modelUrl).toMatch(/^\/models\/.+\.glb$/);
  });
});
