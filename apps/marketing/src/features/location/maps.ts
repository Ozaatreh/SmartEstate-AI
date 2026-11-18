/// <reference types="google.maps" />
export type Lang = "en" | "ar";
export type MapView = "map" | "streetview";

/**
 * Google Maps JavaScript API (https://developers.google.com/maps/documentation/javascript/load-maps-js-api), loaded
 * once, on demand, only for verified locations. The browser key comes from VITE_GOOGLE_MAPS_API_KEY; it is never logged.
 * Libraries are then taken with `google.maps.importLibrary(...)`.
 */
let loading: Promise<void> | null = null;
const authListeners = new Set<() => void>();

export function loadMapsApi(key: string, lang: Lang): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no_window"));
  const g = (window as unknown as { google?: { maps?: { importLibrary?: unknown } } }).google;
  if (g?.maps?.importLibrary) return Promise.resolve();
  if (!loading) {
    loading = new Promise<void>((resolve, reject) => {
      const w = window as unknown as Record<string, unknown>;
      w.__smartestateMapsReady = () => resolve();
      // Google calls this when the key is rejected (invalid, referrer not allowed, API not enabled for the key).
      w.gm_authFailure = () => authListeners.forEach((f) => f());
      const q = new URLSearchParams({ key, v: "weekly", loading: "async", callback: "__smartestateMapsReady", language: lang });
      const s = document.createElement("script");
      s.src = `https://maps.googleapis.com/maps/api/js?${q.toString()}`;
      s.async = true;
      s.onerror = () => { loading = null; s.remove(); reject(new Error("maps_load_failed")); };
      document.head.appendChild(s);
    });
  }
  return loading;
}

/** Subscribe to Google's key-rejection callback. Returns an unsubscribe function. */
export function onMapsAuthFailure(listener: () => void): () => void {
  authListeners.add(listener);
  return () => authListeners.delete(listener);
}

/**
 * Street View availability near the point, via StreetViewService.getPanorama (Maps JavaScript API).
 *  - "available": the nearest Google Street View panorama within 50 m (its id is used so the viewer opens exactly there)
 *  - "unavailable": Google reports no imagery near the point → the site's own fallback
 *  - "unknown": the lookup failed for another reason → shown as an error, never as imagery
 */
export type StreetViewCheck = { status: "available"; pano: string } | { status: "unavailable" } | { status: "unknown" };

export async function findPanorama(service: Pick<google.maps.StreetViewService, "getPanorama">, lat: number, lng: number): Promise<StreetViewCheck> {
  try {
    // Google's own imagery only: "outdoor"/"default" also return user-contributed photo spheres (in testing, a private
    // hotel bathroom next to Kingdom Centre), which must never appear on a property page.
    const { data } = await service.getPanorama({ location: { lat, lng }, radius: 50, sources: ["google" as google.maps.StreetViewSource] });
    const pano = data.location?.pano;
    return pano ? { status: "available", pano } : { status: "unavailable" };
  } catch (e) {
    return (e as { code?: string })?.code === "ZERO_RESULTS" ? { status: "unavailable" } : { status: "unknown" };
  }
}
