# Marketing image assets (brochures & posters)

**Status:** there are **no approved project images**. NOVA Residences is fictional and has **no media entries** (its two
example.com placeholder links — a brochure and a tour that never existed — were removed on 17 Nov 2026, audited, and
dropped from the demo seed). Brochures and posters
therefore use a neutral, text-free placeholder illustration drawn in code (no photo, no third-party asset).

## Rules
- Only images with a recorded **source** and **licence**, explicitly **approved**, are offered in the generator.
- Images are local files; remote URLs are never fetched while rendering.
- No AI-generated or unknown-source property images. Real photos of real buildings must not be used for a fictional
  project.

## How to add an approved image
1. Put the file (JPG, PNG or WebP) under `COLLATERAL_MEDIA_DIR` (default `apps/api/var/media`), e.g. `nova/hero.jpg`.
2. Add an entry to the project's `media` list:
   `{"kind": "image", "file": "nova/hero.jpg", "approved": true, "source": "<who made it>", "licence": "<licence / rights>", "caption": "<optional>"}`
3. The image appears under **Cover image** / **Image** in Dashboard → Marketing → Brochures & posters, and its credit is
   printed on the brochure's back page.

## Assets needed
| Asset | Use | Minimum size |
|---|---|---|
| Hero exterior (landscape) | Brochure cover, LinkedIn/Facebook posters | 2480 × 1650 px |
| Hero exterior (portrait) | Instagram story | 1080 × 1920 px |
| Square exterior or lifestyle | Instagram post | 1080 × 1080 px |
| Amenity image (pool / podium) | Brochure inner page band | 2000 × 900 px |
| Interior (living room) | Brochure back page band | 2000 × 900 px |

For a fictional project these should be renders you commission, or freely licensed illustrative images clearly
captioned as illustrative (design decision D-14), each with source and licence recorded.

## Fonts
Inter, Fraunces and IBM Plex Sans Arabic (SIL Open Font License 1.1) are embedded from
`apps/api/app/modules/marketing/collateral/fonts/` (licence files alongside).

## Website cover image and media kinds
- The website's project cover is the first media entry of kind **Image** whose link is an image (links ending in .pdf,
  .mp4, .html etc. are never used). Local `file` images are for brochures/posters only and are never served publicly.
- Dashboard → project → Edit → **Media** keeps each entry's kind (Image / Brochure / Virtual tour / Video) and saves local
  approved-image entries back unchanged. (Before 17 Nov 2026 the form re-saved every entry as "image", which made NOVA's
  brochure PDF its "cover" and showed a broken image; NOVA's kinds were restored to brochure/tour, audited; those placeholder links were later removed altogether.)
- With no valid image the website shows a neutral branded panel ("Project images coming soon"); an image link that fails
  to load falls back to the same panel.
