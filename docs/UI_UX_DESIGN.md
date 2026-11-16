# SmartEstate AI — UI/UX Design System

> Status: **Phase 0 design direction, awaiting approval (D-14, D-15).** UI quality is a core
> requirement (PROJECT_SPECIFICATION.md § 7a). The tokens and components below are built first in
> Phase 1, and every module after that uses them.

## 1. Design principles

1. **Calm precision.** The quality bar is Linear and Stripe: few colours, exact alignment, generous but
   disciplined white space, typography doing most of the work.
2. **Structure over decoration.** Use 1px borders and spacing to separate content, not shadows or
   gradients. Shadows are only for floating layers (menus, dialogs).
3. **Data first.** Numbers are legible, aligned (tabular figures), formatted with units, and always real.
4. **One system, several moods.** Operations is dense, executive is spacious, property is
   editorial, the studio is a workspace. They share the same tokens and components.
5. **AI is visible and accountable.** AI output is labelled, shows its sources, and its actions
   lead to the normal screens where a person decides.
6. **Every state is designed:** loading, empty, error, success, permission-denied.

## 2. Visual identity — "Najd" (D-15)

The palette is inspired by Riyadh's built environment: deep night ink, warm desert clay and
sand-tinted neutrals. One restrained violet marks AI.

### 2.1 Colour tokens (light theme)

All colours are CSS variables with **semantic names** in `src/styles/tokens.css`, mapped into
Tailwind. Components never use raw hex values. Dark mode later = a `.dark` block that redefines the
same tokens.

| Token | Value | Use |
|---|---|---|
| `--canvas` | `#F7F6F3` | App background (warm off-white) |
| `--surface` | `#FFFFFF` | Cards, tables, panels |
| `--surface-subtle` | `#FBFAF8` | Sidebar, table header, inset areas |
| `--border` | `#E5E2DC` | Default 1px borders |
| `--border-subtle` | `#EEECE7` | Row dividers |
| `--text` | `#0F1A2B` | Primary text (ink) |
| `--text-secondary` | `#4B5563` | Secondary text |
| `--text-muted` | `#6B7280` | Metadata, placeholders (AA on white) |
| `--primary` | `#14213D` | Primary buttons, selected states (night ink) |
| `--primary-foreground` | `#FFFFFF` | Text on primary |
| `--brand` | `#A4532B` | Brand accent (desert clay): active nav marker, links, focus ring, logo (5.4:1 on white) |
| `--brand-subtle` | `#F6ECE6` | Brand tint backgrounds |
| `--ai` | `#5B4BC4` | AI badge, AI panel accents only (6.5:1 on white) |
| `--ai-subtle` | `#EFEDFA` | AI message background |
| `--success` / `--success-subtle` | `#15803D` / `#E8F5EC` | Approved, available, succeeded |
| `--warning` / `--warning-subtle` | `#B45309` / `#FDF3E7` | Pending, reserved, near budget |
| `--danger` / `--danger-subtle` | `#B91C1C` / `#FCEBEB` | Rejected, failed, over budget |
| `--info` / `--info-subtle` | `#1D4ED8` / `#EAF0FD` | In progress, informational |
| `--neutral` / `--neutral-subtle` | `#475569` / `#F1F2F4` | Draft, cancelled, archived |
| `--chart-1…5` | `#1F3A5F`, `#C0703F`, `#3F8F7F`, `#8C7AD9`, `#9AA5B1` | Chart series, in fixed order |

The chart palette gets validated for contrast and colour-vision differences in Phase 1, and any
slot that fails is adjusted before use.

### 2.2 Typography
| Role | Font | Notes |
|---|---|---|
| UI and data | **Inter Variable** (self-hosted) | `font-feature-settings: "tnum", "cv11"` for figures; base size **14px** in Operations, 15px elsewhere |
| Display (property showcase, campaign previews) | **Fraunces** (variable, self-hosted) | Only for large headings in the property and studio experiences: editorial, premium |
| Arabic content | **IBM Plex Sans Arabic** | Arabic marketing text and AI replies, `dir="rtl"` on those blocks only |

Scale (px / line height): 12/16 caption · 13/18 small · 14/20 body · 16/24 lead · 20/28 h3 · 24/32 h2 ·
32/40 h1 · 48/56 display. Weights: 400, 500 (labels and buttons), 600 (headings). Sentence case everywhere.

### 2.3 Shape, spacing, elevation
- 4px spacing grid. Common steps: 4, 8, 12, 16, 24, 32, 48.
- Radius: **6px** controls, **8px** cards/panels, **10px** dialogs. Badges get a pill shape. Nothing rounder.
- Elevation: cards are flat with a 1px border. `--shadow-overlay` (soft, single layer) only on popovers,
  menus, dialogs and toasts.
- Density: table rows 40px (Operations), 48px (comfortable). Inputs 36px, buttons 32/36px.

### 2.4 Iconography and brand mark
- lucide-react icons, 16px in tables and buttons, 20px in navigation, stroke 1.75, `currentColor`.
- Logo: a simple geometric mark (stacked rooflines forming an "S") in `--brand`, plus the wordmark
  "SmartEstate" in Inter 600 with "AI" in `--text-muted`. Delivered as SVG in Phase 1.

### 2.5 Formatting
- Money: `SAR 1,250,000` (no decimals in tables unless needed, two decimals in documents). Negative values use a minus sign and `--danger`.
- Percentages: one decimal (`82.4%`). Dates: `16 Nov 2026`. Relative times for activity ("3 h ago", with the exact time in a tooltip).
- Codes in a monospace-figure style (`PR-00012`) that you can copy on click.

## 3. Application shell

```
┌──────────┬────────────────────────────────────────────────────────────┐
│ ◆ Smart- │  Breadcrumbs / page title          ⌘K search   🔔   avatar │  56px top bar
│ Estate   ├────────────────────────────────────────────────────────────┤
│──────────│  PageHeader: title · description · primary action          │
│ OVERVIEW │  FilterBar / tabs                                          │
│  Dash    │  ┌──────────────────────────────────────────────────────┐  │
│ OPERATNS │  │ content                                              │  │
│  HR …    │  └──────────────────────────────────────────────────────┘  │
│ REAL EST │                                                            │
│ MARKETNG │                                                            │
│ INTELLIG │                                                            │
│ ADMIN    │                                                            │
│ «  user  │                                                            │
└──────────┴────────────────────────────────────────────────────────────┘
 248px / 64px collapsed
```

- **Sidebar:** light (`--surface-subtle`) with a right border. Sections are Overview, Operations (HR,
  Finance, Procurement, Approvals, Automation), Real Estate & Sales (Projects, Units, Leads), Marketing
  (Studio), Intelligence (BI Agent), Administration. The active item has a 2px clay marker and ink text.
  Items the user has no permission for are hidden. Pending approvals and unread notifications show counts.
- **Collapse:** a toggle (and `[` shortcut) switches to a 64px icon rail with tooltips. The state is kept in `localStorage`.
- **Command palette (S):** ⌘K / Ctrl K to jump to pages and records (shadcn `Command`).
- **Public visitor area** uses its own `PublicLayout` (no sidebar, brand header, footer with the
  "fictional demonstration project" notice).

## 4. Experience treatments

| Experience | Layout | Key components | Feel |
|---|---|---|---|
| **Operations** (HR, Finance, Procurement, Approvals, Automation) | `OpsLayout`: full-width tables; list → detail drawer or split view; document pages with a header (code, status, amount, actions) + tabs (Details, Lines, Approval timeline, Activity) | DataTable, StatusBadge, MoneyText, ApprovalTimeline, BudgetBar, DocumentHeader | Dense, exact, keyboard-friendly |
| **Executive Dashboard** | `ExecutiveLayout`: KPI strip (4–6 cards) → 2–3 large ChartCards → "Needs attention" list → AI digest side panel | KpiCard (value, delta vs. previous period, sparkline), ChartCard, AttentionList, AiDigestPanel | Spacious, polished, minimal chrome |
| **Real Estate Projects** | `ShowcaseLayout`: edge-to-edge hero image with project name in Fraunces; facts row; buildings tabs; **availability grid** (floors × units, coloured by status); unit detail sheet with gallery, specs, payment-plan breakdown | Hero, FactRow, AvailabilityGrid, UnitCard, Gallery, PaymentPlanTable | Editorial, premium, imagery-led |
| **Marketing Studio** | `StudioLayout`: three panes. Brief & settings (left) · generated variants as editable cards (centre) · channel preview + approval state (right) | BriefForm, VariantCard (edit, regenerate, compare), ChannelPreview (post / email / web), ApprovalPanel | Creative workspace, focused |
| **AI Assistants** | Docked `ChatPanel` (BI agent, inside the app) and a full-page visitor chat (property assistant) | Streaming message list, ToolActivity ("Checked budget positions · 3 departments"), structured result cards (UnitCard, KpiTable, MiniChart), SourceChips, suggested prompts, AiBadge | Conversational with structured answers |

## 5. Responsive behaviour

| Width | Navigation | Content |
|---|---|---|
| ≥ 1280 (desktop) | Full sidebar (collapsible) | Multi-column layouts, split views |
| 768–1279 (tablet) | Icon rail by default | Two columns become one where needed. The detail drawer covers the content. |
| < 768 (mobile) | Off-canvas sheet from a top-bar menu button | Tables become stacked row cards (primary field, status, amount, chevron); filters go in a bottom sheet; the primary action is in a sticky bottom bar; charts go full width |

Each layout is checked at 1440, 1024 and 390 px wide.

## 6. Core components (design-system layer)

| Component | Contract |
|---|---|
| `DataTable` | TanStack Table. Server-side search (debounced 300 ms), column filters (FilterBar chips), sort, pagination (page size 25), column visibility, row selection when actions exist, row actions menu, sticky header. Filter, sort and page live in the URL query. Loading = skeleton rows, empty = EmptyState, error = ErrorState. |
| `StatusBadge` | Maps every domain status to a tone (`success/warning/danger/info/neutral`) from one table in `lib/status.ts`. Dot + label, no colour-only meaning. |
| `KpiCard` | Label, value (MoneyText/number/percent), delta vs. comparison period with direction icon, optional sparkline, link to source. A loading skeleton has the same height. |
| `ChartCard` | Title, subtitle with period and unit, Recharts chart with token colours, accessible table fallback (toggle), empty state when there are zero rows. |
| `FormField` | Label, control, hint, error (from Zod or a mapped server `details`), required marker. Forms in 1–2 column grids; sticky footer actions on long forms. |
| `EmptyState` / `ErrorState` / `LoadingSkeleton` | Empty: icon, one-sentence explanation, primary next action. Error: message, Retry, request ID (copy). Permission-denied variant. |
| `ConfirmDialog` | Names the action and the record ("Approve PR-00012 for SAR 84,500?"). Destructive actions use the danger tone. |
| `AiBadge`, `ToolActivity`, `SourceChips` | Mark AI content, show which tools ran and on what data, and link to the source screens. |
| Toasts (Sonner) | Success after mutations, errors with a retry where it makes sense. Bottom-right on desktop, top on mobile. |

## 7. States and feedback

- **Loading:** skeletons shaped like the final content (no full-page spinners after first load);
  buttons show an inline spinner and stay disabled while submitting.
- **Empty:** explain why and offer the next step ("No purchase requests yet. Create one").
  A filtered-empty state offers "Clear filters".
- **Error:** inline for a section, full page only when a route fails. Always offer a retry. Show the request ID.
- **Success:** toast + optimistic update where it is safe (never for approvals or financial actions,
  which wait for the server).
- **Streaming AI:** a typing indicator, then text streams in. Tool activity lines appear as they run. Stop button.

## 8. Motion

- Durations 150 ms (hover, press), 200 ms (popover, drawer), 250 ms (page-level fades). Easing `cubic-bezier(0.2, 0, 0, 1)`.
- Allowed: fades, 4–8px slides for overlays, skeleton shimmer, number count-up on KPI first load (≤ 400 ms).
- Not allowed: bouncing, parallax, looping decorative animation. `prefers-reduced-motion` turns transitions into instant changes.
- Implemented with Tailwind transitions and `tw-animate-css` (shadcn default). No extra animation library.

## 9. Imagery (D-14)

- NOVA Residences is fictional, so imagery is **illustrative**: freely licensed architectural photos
  (Unsplash licence) or renders you supply. Files are stored locally in `apps/web/public/media/nova/` and
  credited in `CREDITS.md`, and every image carries a small "Illustrative image" caption.
- Optimised to WebP at 2–3 sizes with `srcset`, lazy-loaded below the fold, fixed aspect ratios (16:9 hero, 4:3 cards) to avoid layout shift.
- Downloading the image set needs your approval (and the list of files) before Phase 5.

## 10. Accessibility

WCAG 2.2 AA contrast for text and UI. Visible 2px `--brand` focus ring with offset. Full keyboard
operation (tables, dialogs, command palette, chat). Labels on every control. `aria-live` for toasts and
streamed AI replies. Charts have a table alternative. Status never relies on colour alone.

## 11. Anti-patterns (rejected in review)

Template-style dashboards with random stat cards · gradient backgrounds or gradient buttons ·
stacked heavy shadows · radius above 10px on cards · different table or button styles per module ·
placeholder charts or "lorem" metrics · pages that are only a form plus a table with no hierarchy ·
colour used without a meaning from the token table.

## 12. UI quality gate (each phase)

1. Uses only `components/system` + tokens; no raw hex or ad-hoc spacing in features.
2. Loading, empty, error and permission states exist and were seen.
3. Checked at 1440 / 1024 / 390 px.
4. Keyboard pass and focus visible.
5. Numbers formatted and sourced from the API.
6. Screenshot recorded for the phase report.
