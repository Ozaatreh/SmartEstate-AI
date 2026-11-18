# 3D property models (Phase 7E)

**Status:** the capability is built; **no 3D models exist yet.** None were supplied and none were generated —
SmartEstate never creates or invents property geometry. Until an approved model is added, project and unit pages show
"A 3D model isn't available yet".

## Supported formats and limits
| | |
|---|---|
| Formats | **glTF 2.0** — binary `.glb` (recommended), or `.gltf` with **all data embedded** (`data:` URIs) |
| Max size | `MODEL_MAX_UPLOAD_MB` (default **50 MB**) |
| Not accepted | external `.bin`/texture files, remote URLs, glTF 1.0, models without meshes, and required extensions the viewer can't decode: Draco, meshopt, KTX2/Basis, WebP/AVIF textures (export without these compressions) |

Every upload is validated **on the server**: the file's bytes decide the format (not the browser's content type), the GLB
header and chunks are checked, the glTF JSON is parsed, and any external reference is refused. Errors come back with a
specific code (`model_too_large`, `external_resources`, `unsupported_extension`, …).

## Managing models (Dashboard → Real estate → project → **3D models**)
Needs `realestate.inventory.manage` (Sales Manager, Super Admin). Other staff with `realestate.inventory.read` can view
the list and download files; the public can't reach any of this.

1. **Add model** — title, what it represents (*Design model*, *As built*, *Illustrative*), optional unit, caption, and
   the **source** and **licence**.
2. **Upload file** (`.glb` / `.gltf`). Uploading again **replaces** the file (the old file is deleted once the new one
   is saved) and sends the model back to *draft*.
3. **Download** it to check it, then **Approve**. Approval needs a validated file plus source and licence; who approved
   it and when is recorded. Editing an approved model's details also sends it back to draft.
4. **Archive** to take it off the website (**Restore** → draft). Draft and archived models can be **deleted** (record and
   file). All actions are in the audit log.

## What the public sees
A model is shown — and its file served — only when it is **approved**, its project is **published**, and (for a unit
model) the unit is **public**. Anything else returns the same 404. Project pages show project-level models; unit pages
show that unit's models. The page always states what the model represents ("Illustrative model — indicative only…"),
credits its source and licence, and keeps the fictional-project disclosure for demo projects.

The file URL is `/api/v1/public/models/{id}/file` — read-only, `nosniff`, with no storage path, file name or
uploader exposed. Files live in `MODEL_STORAGE_DIR` (default `apps/api/var/models`, git-ignored) under random names.

## The viewer
three.js (MIT), loaded only when a visitor taps **View the 3D model** (the main site bundle doesn't grow). Drag to
orbit, scroll/pinch or the +/− buttons to zoom, ↺ to reset; loading progress, load errors (with retry) and devices
without WebGL are handled. No external services, CDNs or API keys.

## Adding an approved model later
1. Get the model from its creator (architect, visualisation studio) **with written permission** to show it publicly.
2. Export glTF 2.0 as a single `.glb`; no Draco/meshopt compression; keep it under the size limit (aim for < 20 MB so
   it loads well on mobile); real-world scale in metres, Y up.
3. In the dashboard: Add model → choose what it honestly represents → record source and licence → upload → download and
   check → Approve.
4. For a fictional demo project such as NOVA, only an explicitly **illustrative** model is appropriate.

## Configuration
```
MODEL_STORAGE_DIR=var/models     # relative to apps/api
MODEL_MAX_UPLOAD_MB=50
```
In production, back up this folder with the database (records and files go together).
