import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import * as api from "./api";
import type { MediaItem } from "./api";
import { coverIndex, imageFileProblem, mediaError, mediaPayload, mediaRows, type MediaRow } from "./logic";
import { MediaEditor } from "./media-editor";

const NOVA: MediaItem[] = [
  { url: "https://example.com/nova/brochure.pdf", kind: "brochure", caption: "Project brochure" },
  { url: "https://example.com/nova/tour", kind: "tour" },
  { kind: "image", file: "nova/hero.jpg", approved: true, source: "Studio X", licence: "Licensed", caption: "Render" },
];

describe("project media editing", () => {
  it("saves every entry back with its own kind, and local images unchanged", () => {
    // The old form re-saved everything as kind "image", which turned NOVA's brochure PDF into its cover image.
    expect(mediaPayload(mediaRows(NOVA))).toEqual([
      { url: "https://example.com/nova/brochure.pdf", kind: "brochure", caption: "Project brochure" },
      { url: "https://example.com/nova/tour", kind: "tour", caption: null },
      NOVA[2],
    ]);
  });

  it("validates links and drops empty rows", () => {
    expect(mediaError([{ key: "a", url: "ftp://x", caption: "", kind: "image" }])).toMatch(/http/);
    expect(mediaPayload([{ key: "a", url: "  ", caption: "", kind: "image" }])).toEqual([]);
  });

  it("edits kinds per row and keeps uploaded images' stored fields", async () => {
    function Harness() {
      const [rows, setRows] = React.useState<MediaRow[]>(mediaRows(NOVA));
      return <><MediaEditor rows={rows} onChange={setRows} projectId="p1" /><output data-testid="out">{JSON.stringify(mediaPayload(rows))}</output></>;
    }
    render(<Harness />);
    expect(screen.getByRole("img", { name: "Render" })).toHaveAttribute("src", "/api/v1/realestate/projects/p1/media/file?file=nova%2Fhero.jpg");
    expect(screen.getByRole("combobox", { name: "Media 1 kind" })).toHaveTextContent("Brochure");
    await userEvent.click(screen.getByRole("button", { name: /add media link/i }));
    await userEvent.type(screen.getByRole("textbox", { name: "Media 4 link" }), "https://cdn.example/front.webp");
    await userEvent.click(screen.getByRole("button", { name: "Remove media 2" }));
    const out = JSON.parse(screen.getByTestId("out").textContent!) as MediaItem[];
    expect(out.map((m) => m.kind)).toEqual(["brochure", "image", "image"]);
    expect(out[1]).toEqual(NOVA[2]);
    expect(out[2]).toEqual({ url: "https://cdn.example/front.webp", caption: null, kind: "image" });
  });

  it("marks the website cover (first approved image) and moves another image to the top", async () => {
    const media: MediaItem[] = [
      { url: "https://example.com/brochure.pdf", kind: "image" }, // a PDF is never the cover
      { url: "https://example.com/old.jpg", kind: "image" },
      { kind: "image", file: "projects/nova/a.png", approved: true, source: "Studio X", licence: "Licensed" },
    ];
    expect(coverIndex(mediaRows(media))).toBe(1);
    function Harness() {
      const [rows, setRows] = React.useState<MediaRow[]>(mediaRows(media));
      return <><MediaEditor rows={rows} onChange={setRows} projectId="p1" /><output data-testid="out">{JSON.stringify(mediaPayload(rows))}</output></>;
    }
    render(<Harness />);
    expect(screen.getAllByText("Website cover")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Set media 3 as cover" }));
    const out = JSON.parse(screen.getByTestId("out").textContent!) as MediaItem[];
    expect(out[0]!.file).toBe("projects/nova/a.png");
  });

  it("uploads an image from the device; it is approved only with a source and licence", async () => {
    const upload = vi.spyOn(api, "uploadProjectImage").mockResolvedValue({ file: "projects/nova/new.png", id: "abc", size_bytes: 10 });
    function Harness() {
      const [rows, setRows] = React.useState<MediaRow[]>([]);
      return <><MediaEditor rows={rows} onChange={setRows} projectId="p1" /><output data-testid="err">{mediaError(rows) ?? ""}</output>
        <output data-testid="out">{JSON.stringify(mediaPayload(rows))}</output></>;
    }
    render(<Harness />);
    await userEvent.upload(screen.getByTestId("image-file"), new File(["x"], "render.png", { type: "image/png" }));
    expect(upload).toHaveBeenCalledWith("p1", expect.any(File));
    expect(await screen.findByTestId("uploaded-image")).toBeInTheDocument();
    expect(JSON.parse(screen.getByTestId("out").textContent!)).toEqual([{ kind: "image", file: "projects/nova/new.png", approved: false }]);
    await userEvent.click(screen.getByRole("checkbox", { name: "Approve media 1" }));
    expect(screen.getByTestId("err")).toHaveTextContent("An approved image needs its source and licence.");
    await userEvent.type(screen.getByRole("textbox", { name: "Media 1 source" }), "Studio X");
    await userEvent.type(screen.getByRole("textbox", { name: "Media 1 licence" }), "Licensed for marketing");
    expect(screen.getByTestId("err")).toBeEmptyDOMElement();
    expect(JSON.parse(screen.getByTestId("out").textContent!)).toEqual([
      { kind: "image", file: "projects/nova/new.png", approved: true, source: "Studio X", licence: "Licensed for marketing" },
    ]);
    expect(screen.getByText("Website cover")).toBeInTheDocument();
  });

  it("refuses unsupported or oversized files before uploading, and needs a saved project", () => {
    expect(imageFileProblem(new File(["x"], "a.gif", { type: "image/gif" }))).toMatch(/JPEG, PNG or WebP/);
    expect(imageFileProblem(new File([new Uint8Array(10 * 1024 * 1024 + 1)], "a.jpg", { type: "image/jpeg" }))).toMatch(/10 MB/);
    render(<MediaEditor rows={[]} onChange={() => undefined} />);
    expect(screen.getByRole("button", { name: /upload image/i })).toBeDisabled();
    expect(screen.getByText("Save the project first to upload images.")).toBeInTheDocument();
  });
});
