import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fileProblem, type PropertyModel } from "./models3d-api";
import { ModelsPanel } from "./models3d-panel";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const file = (name: string, size: number) => new File([new Uint8Array(size)], name);

const MODEL: PropertyModel = {
  id: "m1", project_id: "p1", unit_id: null, unit_code: null, title: "Tower A design", caption: null, representation: "design",
  source: "Architect", licence: "Licensed", status: "draft", format: "glb", size_bytes: 2_400_000, sha256: "x", original_filename: "a.glb",
  mesh_count: 12, file_version: 1, uploaded_at: "2026-11-17T10:00:00Z", uploaded_by: { id: "u", full_name: "Sara Manager" },
  approved_at: null, approved_by: null, created_at: "", updated_at: "", publicly_visible: false,
  allowed_actions: ["download", "edit", "upload", "approve", "archive", "delete"],
};

function show(models: PropertyModel[], canManage: boolean) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith("/limits") ? { formats: [".glb", ".gltf"], max_bytes: 50 * 1024 * 1024 } : models), { headers: { "Content-Type": "application/json" } })));
  render(<QueryClientProvider client={new QueryClient()}><ModelsPanel projectId="p1" canManage={canManage} isDemo /></QueryClientProvider>);
}

describe("3D model management", () => {
  it("checks files before uploading (the API re-validates)", () => {
    expect(fileProblem(file("tower.obj", 1000))).toMatch(/\.glb or \.gltf/);
    expect(fileProblem(file("tower.glb", 10))).toMatch(/too small/);
    expect(fileProblem(file("tower.glb", 2000), { formats: [], max_bytes: 1000 })).toMatch(/larger than/);
    expect(fileProblem(file("Tower.GLTF", 2000))).toBeNull();
  });

  it("shows status, provenance and only the actions the API allows", async () => {
    show([MODEL], true);
    expect(await screen.findByText("Tower A design")).toBeInTheDocument();
    expect(screen.getByText("Not public")).toBeInTheDocument();
    expect(screen.getByText(/GLB · 2.3 MB · 12 meshes · v1/)).toBeInTheDocument();
    expect(screen.getByText("Source: Architect · Licence: Licensed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /replace file/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /restore/i })).not.toBeInTheDocument();
    expect(screen.getByText(/never present invented geometry as a real building/)).toBeInTheDocument();
  });

  it("is read-only without the manage permission", async () => {
    show([{ ...MODEL, status: "approved", publicly_visible: true, allowed_actions: ["download"] }], false);
    expect(await screen.findByText("On the website")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add model|approve|edit|archive|replace/i })).not.toBeInTheDocument();
  });
});
