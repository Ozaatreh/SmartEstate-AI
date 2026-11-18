# SmartEstate AI: assessment presentation

A self-contained, animated HTML deck of 21 slides explaining the SmartEstate AI prototype to an assessment panel
(Business Transformation & AI Specialist). It works offline: fonts, screenshots and the logo are all in `assets/`.
No CDN and no build step are needed.

## Run it

Open `index.html` in a current Chrome, Edge, Firefox or Safari. Double-clicking the file works.

To serve it over HTTP instead (optional):

```bash
cd presentation
python -m http.server 8080      # then open http://localhost:8080
```

Deep links: `index.html#9` opens slide 9.

## Controls

| Key | Action |
|---|---|
| `→` `Space` `PageDown` `Enter` | Next step or slide (slide 9 builds its four flows one at a time) |
| `←` `Shift+Space` `PageUp` `Backspace` | Previous |
| `↑` `↓` | Previous / next (on narrow screens they scroll a long slide) |
| `Home` / `End` | First / last slide |
| `F` | Full screen on or off (also the ⤢ button) |
| digits then `Enter` | Jump to a slide, e.g. `1` `4` `Enter` |
| `?` / `Esc` | Show / close the shortcuts panel |
| Swipe left / right | Next / previous on touch screens |

The bottom bar shows the slide counter, a dot for each slide (click to jump), previous/next/full-screen/help buttons and a
progress line. Motion respects `prefers-reduced-motion`.

## PDF

`SmartEstate-AI-presentation.pdf` has one 1600 × 900 page per slide, with every reveal shown. To regenerate it:

```bash
cd presentation
../apps/api/.venv/Scripts/python export_pdf.py
```

Printing from the browser also works (Ctrl+P, background graphics on), because the print stylesheet lays out one slide per page.

## PowerPoint version

`SmartEstate-AI-presentation.pptx` (16:9) holds the same 21 slides, built from native PowerPoint objects: text boxes,
shapes, connectors, tables and one native bar chart (slide 19), so the text and diagrams are editable. The screenshots
are picture objects, and the zoomed callouts are separate cropped pictures. Every slide has speaker notes and a
0.6 s Fade transition. Fonts: Georgia (headings) and Calibri (body), which ship with Office, instead of the web fonts.
It was opened, checked for text overflow, rendered and saved in PowerPoint 16 (Microsoft 365) through COM automation.

## Layout

- **Desktop / landscape:** a fluid 16:9 stage that scales with the window (checked at 1920×1080, 1440×900, 1366×768 and 1280×720).
- **Phone / portrait tablet** (≤ 900 px wide or portrait): each slide becomes a vertical page you scroll, and diagrams
  switch to stacked versions (checked at 390×844 and 768×1024).

## Slides

1 Opening · 2 Business challenge · 3 Vision · 4 Specified scope vs. delivered · 5 System overview · 6 Business operations ·
7 Real-estate portfolio · 8 CRM & customer journey · 9 Four core workflows (progressive) · 10 Python automation engine ·
11 AI architecture · 12 AI use cases and their status · 13 Technology stack · 14 Architecture & data flow ·
15 Security, governance & reliability · 16 Added beyond the assessment · 17 Inside the staff dashboard (screens) ·
18 The public experience (screens) · 19 Testing · 20 Limitations & opportunities · 21 Closing

## Sources and accuracy

- **Requirements baseline:** the original assessment brief isn't in the repository, so slide 4 uses
  `docs/PROJECT_SPECIFICATION.md` § 5 (modules and priorities). It doesn't invent requirements.
- **Versions** are the installed ones (`node_modules/*/package.json`, `pip list`, `SELECT version()`), on 18 Nov 2026.
- **Counts** (tables, migrations, roles, permissions, workflows, executions, `ai_usage` rows) were read from the
  development database in a read-only transaction on 18 Nov 2026.
- **Tests** were run on 18 Nov 2026 against the uncommitted working tree:

  | Suite | Result |
  |---|---|
  | Backend pytest | 352 passed (96 unit, 256 PostgreSQL integration) |
  | Dashboard Vitest | 73 passed (17 files) |
  | Website Vitest | 44 passed (4 files) |
  | Checks | Ruff, ESLint and `tsc -b` clean in both apps. Production builds were not re-run. |
- **No AI call** was made for this deck. "Live calls logged" means rows in `ai_usage`.
- **Screenshots** (`assets/shots/`, 1440×900 at 2× scale) were captured from the running apps. E-mail addresses and phone
  numbers were masked in the page before capture. NOVA Residences is fictional demo data, and every slide says so.
  Two images in the current data were kept out of the deck on purpose: NOVA's website cover (a third-party image link
  with no recorded licence) and a brochure-only test image labelled "chgpt". The brochure-generator screenshot is
  cropped so it doesn't show that image.

## Files

```
presentation/
├─ index.html                       the deck (HTML, CSS and JS inline)
├─ SmartEstate-AI-presentation.pdf  PDF export
├─ SmartEstate-AI-presentation.pptx editable PowerPoint version (same 21 slides, speaker notes)
├─ export_pdf.py                    regenerates the PDF
├─ README.md
└─ assets/
   ├─ logo.svg                      copied from apps/marketing/public/favicon.svg
   ├─ fonts/                        Fraunces, Inter, IBM Plex Sans Arabic (SIL OFL 1.1, from @fontsource)
   └─ shots/                        20 screenshots used by the slides
```
