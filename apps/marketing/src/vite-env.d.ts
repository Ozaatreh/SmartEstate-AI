/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Google Maps JavaScript API browser key (restricted to this site's referrers). Optional: without it the site shows text + links. */
  readonly VITE_GOOGLE_MAPS_API_KEY?: string;
  /** Map ID for Advanced Markers. Defaults to Google's DEMO_MAP_ID; use your own Map ID in production. */
  readonly VITE_GOOGLE_MAPS_MAP_ID?: string;
  /** "enabled" to show Street View. Needs a key on a billed Google Cloud project; the Maps Demo Key does not include it. */
  readonly VITE_GOOGLE_MAPS_STREET_VIEW?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
