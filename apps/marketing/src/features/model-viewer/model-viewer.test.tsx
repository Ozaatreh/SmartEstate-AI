import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PublicModel } from "@/lib/api";
import { ModelSection } from "./model-section";
import ModelViewer from "./model-viewer";
import { ViewerOverlay } from "./viewer-overlay";

vi.mock("./model-viewer", () => ({
  default: ({ url, title }: { url: string; title: string }) => <div data-testid="viewer" data-url={url}>{title}</div>,
}));

afterEach(() => vi.restoreAllMocks());

const MODEL: PublicModel = {
  id: "m1", title: "Masterplan", caption: "Both towers and the podium.", representation: "illustrative", credit: "Studio X · Licensed for marketing",
  format: "glb", size_bytes: 2_400_000, file_url: "/api/v1/public/models/m1/file?v=1", unit_code: null,
};

const section = (models: PublicModel[], isDemo = false) =>
  render(<MemoryRouter><ModelSection models={models} isDemo={isDemo} enquireHref="/request-viewing?project=NOVA" /></MemoryRouter>);

describe("3D model section", () => {
  it("renders nothing without approved models (the old \"isn't available yet\" placeholder is gone)", () => {
    const { container } = section([]);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText(/isn't available yet/)).not.toBeInTheDocument();
  });

  it("labels what the model represents, credits it, keeps the demo disclosure and loads only on request", async () => {
    section([MODEL], true);
    expect(screen.getByText("Illustrative model.")).toBeInTheDocument();
    expect(screen.getByText(/not an exact representation/)).toBeInTheDocument();
    expect(screen.getByText(/this model does not depict a real building/)).toBeInTheDocument();
    expect(screen.getByText("Model: Studio X · Licensed for marketing")).toBeInTheDocument();
    expect(screen.queryByTestId("viewer")).not.toBeInTheDocument(); // nothing downloaded yet
    await userEvent.click(screen.getByRole("button", { name: /view the 3d model/i }));
    expect(await screen.findByTestId("viewer")).toHaveAttribute("data-url", MODEL.file_url);
  });

  it("lets visitors switch between several models", async () => {
    section([MODEL, { ...MODEL, id: "m2", title: "A-102 interior", representation: "design", unit_code: "A-102", file_url: "/api/v1/public/models/m2/file?v=3" }]);
    await userEvent.click(screen.getByRole("tab", { name: "A-102 interior" }));
    expect(screen.getByText("Architectural design model.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /view the 3d model/i }));
    expect(await screen.findByTestId("viewer")).toHaveAttribute("data-url", "/api/v1/public/models/m2/file?v=3");
  });
});

describe("viewer states", () => {
  it("shows loading progress, errors with retry, and missing WebGL", async () => {
    const retry = vi.fn();
    const { rerender } = render(<ViewerOverlay status="loading" progress={42} onRetry={retry} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading 3D model · 42%");
    rerender(<ViewerOverlay status="error" progress={null} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("The 3D model couldn't be loaded.");
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(retry).toHaveBeenCalled();
    rerender(<ViewerOverlay status="unsupported" progress={null} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("3D isn't available on this device.");
    rerender(<ViewerOverlay status="ready" progress={null} onRetry={retry} />);
    expect(screen.getByText(/drag to rotate/i)).toBeInTheDocument();
  });
});

describe("real viewer component", async () => {
  const Real = (await vi.importActual<{ default: typeof ModelViewer }>("./model-viewer")).default;

  it("reports missing WebGL instead of failing", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    render(<Real url="/api/v1/public/models/m1/file" title="Masterplan" />);
    expect(screen.getByRole("alert")).toHaveTextContent("3D isn't available on this device.");
  });

  it("refuses to load anything but a public model URL", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as never);
    render(<Real url="https://evil.example/model.glb" title="x" />);
    expect(screen.getByRole("alert")).toHaveTextContent("couldn't be loaded");
  });
});
