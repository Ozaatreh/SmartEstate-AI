# Maps (Phase 7D)

## What the website shows
| Project location | Public project page |
|---|---|
| Verified coordinates **and** `VITE_GOOGLE_MAPS_API_KEY` set | **Map / Street View** switch + **Get directions** + **Open in Google Maps**. *Map*: interactive Google map (zoom, pan, full screen) with a pin on the point. *Street View* (only when `VITE_GOOGLE_MAPS_STREET_VIEW=enabled`): Google's Street View panorama inside the page (look around, move along streets); "Street View imagery isn't available at this location" when Google has none within 50 m; with Street View disabled, "Street View isn't available on this website yet". If Google can't load or rejects the key: a short note, links kept |
| Verified coordinates, no key | Address, coordinates, a note that the interactive map isn't available, and both Google Maps links |
| Not verified (or no coordinates) | District / city / country text only, with a note — no map, no pin, no directions |
| Fictional demo project (e.g. NOVA) | Always the "not verified" view: a fictional project is never pinned to a real place (enforced in the API **and** by a database CHECK) |

The project page's location section is bilingual: `/projects/NOVA?lang=ar` shows it in Arabic, right-to-left
(IBM Plex Sans Arabic). The rest of the site is English for now.

## Location data (Dashboard → Real estate → project → Edit → "Location (maps)")
Fields: address, country, latitude (-90..90), longitude (-180..180), up to 6 decimals, both or neither, and
**Location verified** — tick only after checking the coordinates against an official source. Who verified it and when is
recorded and audited; changing the coordinates clears "verified" until it is confirmed again. Requires
`realestate.inventory.manage` (Sales Manager, Super Admin). The public API returns the exact address, coordinates and
links only for verified locations, and never who verified them.

**Current data (17 Nov 2026):** no project has verified coordinates. NOVA Residences is
fictional demo data. On 17 Nov a dashboard edit saved a *draft* location on it — address "Al Aqiq, Riyadh 13511, Saudi
Arabia", country "Riyadh", 24.757204, 46.631072 — which stays private (not verified; demo projects can't be verified, by
API rule and database CHECK). The NOVA page shows only its labelled illustrative point (see below). Those values describe a real place
in Riyadh, not a NOVA site (NOVA doesn't exist), and "Riyadh" is in the country field. Showing NOVA's *own* pin needs a
data decision first — see "NOVA and maps" below. ACC51 is unpublished.
To show a map for a real project, complete: `address`, `country`, `latitude`, `longitude`, then tick `location_verified`.

## Google Maps configuration
- **Directions / open links** use [Google Maps URLs](https://developers.google.com/maps/documentation/urls/get-started):
  no API key, no billing.
- **Map and Street View** use the [Maps JavaScript API](https://developers.google.com/maps/documentation/javascript/load-maps-js-api),
  loaded on demand (async bootstrap, `v=weekly`) only when a verified location is shown:
  `Map` (zoom 16, cooperative gestures) + `AdvancedMarkerElement` (needs a Map ID: `VITE_GOOGLE_MAPS_MAP_ID`, default
  Google's `DEMO_MAP_ID`), and `StreetViewService.getPanorama` (50 m, **Google imagery only** — the `outdoor`/default
  sources also return user-contributed photo spheres; in testing, a private hotel bathroom) + `StreetViewPanorama`.
  The key is read from `VITE_GOOGLE_MAPS_API_KEY`, never hardcoded or logged; Google's `gm_authFailure` switches the
  panel to its error state.
- The Maps Embed API and Street View Static API are **no longer used**.

### Maps Demo Key (current setup, 17 Nov 2026)
`apps/marketing/.env.local` (git-ignored) holds a Google **Maps Demo Key** with `VITE_GOOGLE_MAPS_STREET_VIEW=disabled`.
Google's [demo-key page](https://developers.google.com/maps/documentation/javascript/demo-key) lists Maps JavaScript API
map rendering, markers and styling (plus some Places/Geocoding/Routes web services); the key "is not designed for
production use", has usage limits, and pauses (no charges) when they are reached. Street View is **not** listed.
Tested in the browser with this key:
- **Map: works** — tiles, pin (Advanced Marker with `DEMO_MAP_ID`), zoom/pan, full screen, desktop and mobile.
- **Street View: not available with the demo key.** `getPanorama` lookups answer, but opening a panorama shows Google's
  "This page can't load Google Maps correctly" dialog, a "For development purposes only" watermark, and the console
  error "You must enable Billing on the Google Cloud Project". So Street View stays disabled; the tab says so.

### Production key
1. Google Cloud Console → project → attach a billing account (needed for Street View and any production use).
2. Enable **Maps JavaScript API**. Create an API key and a **Map ID** (Map Management) for the pin.
3. Restrict the key: *API restrictions* → **Maps JavaScript API** only; *Application restrictions* → **Websites** →
   your site's referrers (e.g. `https://www.example.com/*`, and `http://localhost:5173/*` for development). Set quotas
   and budget alerts.
4. `apps/marketing/.env.local` (or the hosting provider's build env): `VITE_GOOGLE_MAPS_API_KEY=...`,
   `VITE_GOOGLE_MAPS_MAP_ID=...`, and `VITE_GOOGLE_MAPS_STREET_VIEW=enabled`; rebuild. Never commit it, and don't put it
   in the API's `.env` — the backend never sees or logs it. Dynamic Street View is a billed SKU: check current pricing.

This is a browser key: it necessarily appears in the page that loads the map, which is why the restrictions in step 3
matter. It never goes through the API or the dashboard. No other map provider is used.

## Nearby places
Not implemented: there is no reliable nearby-places data in the system, and adding one would need a paid Places API.
Nothing about nearby schools, hospitals, malls or distances is shown or invented.

## Illustrative map point (migration 0015)
A project whose own location isn't verified may show a **labelled reference place** instead — stored separately in
`illustrative_label`, `illustrative_latitude`, `illustrative_longitude` and `illustrative_source` (internal), edited in
Dashboard → project → Edit → "Illustrative map point" (`realestate.inventory.manage` only).
- Never the property's address: `address`, `latitude`, `longitude` and `location_verified` are untouched and keep their
  rules (fictional projects still can't be verified).
- Public API: `location.illustrative = {label, latitude, longitude, notice, directions_url, maps_url}` — no source;
  the property's own `address`/`latitude`/`directions_url` stay `null`. Not given to the public assistant (its
  project tool never includes `location`).
- Website: banner "Illustrative Location — Not the Actual Property Location." (Arabic: «موقع توضيحي — ليس الموقع
  الفعلي للعقار.»), an "Illustrative location" badge on the map, and links "Directions to <label> (reference point)" /
  "Open <label> in Google Maps".
- Rules (API + database CHECKs): coordinates in range and paired; a label whenever coordinates are set; never together
  with a verified location (a verified location is always shown instead).

**NOVA (17 Nov 2026):** reference point **Kingdom Centre, Riyadh — 24.711389, 46.674439** (Wikidata Q656743;
Wikipedia gives 24.7113, 46.6744; King Fahad Road, al-Olaya), set through the dashboard (audited). NOVA remains fictional
demo data and unverified. Its earlier draft location (Al Aqiq…, private) is unchanged.

## NOVA and maps — decision required
NOVA is `is_demo_data` (fictional), so its location can't be verified and no map is shown. Nothing was changed
automatically. To show a map on NOVA, the product owner must choose one of:
1. **Keep NOVA fictional (current).** No map. Optionally clear the draft location (or at least fix `country` →
   "Saudi Arabia") so the page doesn't read "Riyadh, Riyadh".
2. **Make NOVA a realistic demonstration of a real site.** Needs: the real development it represents, written permission
   to market it, an official source for the coordinates (e.g. title deed / municipality plan) and someone accountable to
   verify them; then remove the "fictional" wording from its name/district/description and set `is_demo_data = false`
   (a data change the dashboard deliberately does not offer), and only then tick *Location verified*.
3. **Add a separate, real project** with verified coordinates, and leave NOVA fictional.

## Testing
Automated tests (Google mocked) cover Map mode, Street View (available, no imagery, disabled), load failure and key
rejection, the missing-key fallback, Arabic,
link and coordinate validation, and that unverified locations never render a map or call Google. Real Google tiles and
panoramas were checked in the browser with the Maps Demo Key (see above).
