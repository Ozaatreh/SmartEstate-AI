/// <reference types="google.maps" />
import { AlertTriangle, EyeOff, Loader2, Map as MapIcon, Navigation2 } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";
import { findPanorama, loadMapsApi, onMapsAuthFailure, type Lang, type MapView, type StreetViewCheck } from "./maps";

const T = {
  views: { en: "Map view", ar: "طريقة العرض" },
  map: { en: "Map", ar: "الخريطة" },
  streetview: { en: "Street View", ar: "التجوّل الافتراضي" },
  mapLabel: { en: "Interactive map of", ar: "خريطة تفاعلية لـ" },
  svLabel: { en: "Street View near", ar: "التجوّل الافتراضي قرب" },
  loading: { en: "Loading the map…", ar: "جارٍ تحميل الخريطة…" },
  checking: { en: "Looking for Street View imagery…", ar: "جارٍ البحث عن صور التجوّل الافتراضي…" },
  noImagery: { en: "Street View imagery isn't available at this location.", ar: "صور التجوّل الافتراضي غير متوفرة لهذا الموقع." },
  svError: { en: "Street View couldn't be loaded.", ar: "تعذّر تحميل التجوّل الافتراضي." },
  svOff: { en: "Street View isn't available on this website yet.", ar: "التجوّل الافتراضي غير متاح على هذا الموقع حالياً." },
  mapError: {
    en: "The interactive map couldn't be loaded. Use the links below to open the location in Google Maps.",
    ar: "تعذّر تحميل الخريطة التفاعلية. استخدم الروابط أدناه لفتح الموقع في خرائط Google.",
  },
  backToMap: { en: "Back to the map", ar: "العودة إلى الخريطة" },
} as const;

const FRAME = "h-[300px] w-full sm:h-[360px] lg:h-[420px]";
type Status = "loading" | "ready" | "error";
type SvState = "idle" | "checking" | "ready" | "unavailable" | "error";

/**
 * Google Maps JavaScript API map with a Map / Street View switch (zoom, pan, Street View navigation).
 * Only rendered for verified locations with a browser key; the point comes from the public API.
 * `streetView` must be explicitly enabled: Google requires billing for Street View (the Maps Demo Key doesn't cover it),
 * so with it off the tab explains that Street View isn't available instead of loading a degraded viewer.
 */
export function MapPanel({ lat, lng, apiKey, mapId, lang, projectName, streetView, badge }: {
  lat: number; lng: number; apiKey: string; mapId: string; lang: Lang; projectName: string; streetView: boolean;
  /** Label drawn over the map and Street View (e.g. "Illustrative location"). */
  badge?: string;
}) {
  const [view, setView] = React.useState<MapView>("map");
  const [mapStatus, setMapStatus] = React.useState<Status>("loading");
  const [sv, setSv] = React.useState<SvState>("idle");
  const mapEl = React.useRef<HTMLDivElement>(null);
  const svEl = React.useRef<HTMLDivElement>(null);
  const svStarted = React.useRef(false);

  // The map: created once, as soon as the panel mounts.
  React.useEffect(() => {
    let cancelled = false;
    const off = onMapsAuthFailure(() => { if (!cancelled) { setMapStatus("error"); setSv((s) => (s === "idle" ? s : "error")); } });
    loadMapsApi(apiKey, lang)
      .then(async () => {
        const [{ Map }, { AdvancedMarkerElement }] = await Promise.all([
          google.maps.importLibrary("maps") as Promise<google.maps.MapsLibrary>,
          google.maps.importLibrary("marker") as Promise<google.maps.MarkerLibrary>,
        ]);
        if (cancelled || !mapEl.current) return;
        const position = { lat, lng };
        const map = new Map(mapEl.current, {
          center: position, zoom: 16, mapId, streetViewControl: false, fullscreenControl: true, mapTypeControl: false,
          gestureHandling: "cooperative", clickableIcons: false,
        });
        new AdvancedMarkerElement({ map, position, title: projectName });
        setMapStatus("ready");
      })
      .catch(() => { if (!cancelled) setMapStatus("error"); });
    return () => { cancelled = true; off(); };
  }, [apiKey, lang, lat, lng, mapId, projectName]);

  // Street View: looked up the first time a visitor opens the tab.
  React.useEffect(() => {
    if (!streetView || view !== "streetview" || svStarted.current || mapStatus !== "ready") return;
    svStarted.current = true;
    let cancelled = false;
    Promise.resolve()
      .then(() => { setSv("checking"); return google.maps.importLibrary("streetView") as Promise<google.maps.StreetViewLibrary>; })
      .then(async ({ StreetViewService, StreetViewPanorama }) => {
        const found: StreetViewCheck = await findPanorama(new StreetViewService(), lat, lng);
        if (cancelled) return;
        if (found.status !== "available") return setSv(found.status === "unavailable" ? "unavailable" : "error");
        if (!svEl.current) return;
        new StreetViewPanorama(svEl.current, {
          pano: found.pano, pov: { heading: 0, pitch: 0 }, zoom: 0, addressControl: false, fullscreenControl: true,
          motionTracking: false, motionTrackingControl: false,
        });
        setSv("ready");
      })
      .catch(() => { if (!cancelled) setSv("error"); });
    return () => { cancelled = true; };
  }, [streetView, view, mapStatus, lat, lng]);

  const tab = (v: MapView, Icon: typeof MapIcon) => (
    <button type="button" role="tab" id={`map-tab-${v}`} aria-selected={view === v} aria-controls="map-view-panel" onClick={() => setView(v)}
      disabled={mapStatus === "error"}
      className={cn("inline-flex h-9 items-center gap-1.5 rounded-full px-3.5 text-small font-medium transition-colors disabled:opacity-50",
        view === v ? "bg-surface text-fg shadow-sm" : "text-fg-secondary hover:text-fg")}>
      <Icon className="size-4" aria-hidden />{T[v][lang]}
    </button>
  );

  if (mapStatus === "error") {
    return (
      <p className="mt-4 flex gap-2 rounded-[var(--radius-control)] border border-dashed border-border-strong bg-surface-subtle p-4 text-small text-fg-secondary"
        role="note" data-testid="map-error">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />{T.mapError[lang]}
      </p>
    );
  }

  const overlay = (content: React.ReactNode, role: "status" | "note" | "alert" = "status", testId?: string) => (
    <div className={cn(FRAME, "absolute inset-0 grid place-items-center bg-surface-subtle p-6 text-center")} role={role} data-testid={testId}>{content}</div>
  );

  return (
    <div className="mt-4" data-testid="map">
      <div role="tablist" aria-label={T.views[lang]} className="inline-flex gap-1 rounded-full border border-border bg-surface-subtle p-1">
        {tab("map", MapIcon)}
        {tab("streetview", Navigation2)}
      </div>
      <div id="map-view-panel" role="tabpanel" aria-labelledby={`map-tab-${view}`}
        className={cn("relative mt-3 overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface-subtle", FRAME)}>
        <div ref={mapEl} className={cn(FRAME, view !== "map" && "invisible")} role="region" aria-label={`${T.mapLabel[lang]} ${projectName}`} data-testid="map-canvas" />
        <div ref={svEl} className={cn(FRAME, "absolute inset-0", view !== "streetview" && "invisible")} role="region"
          aria-label={`${T.svLabel[lang]} ${projectName}`} data-testid="streetview-canvas" />
        {badge && (
          <span className="pointer-events-none absolute left-2 top-2 z-10 rounded-full bg-warning px-2.5 py-1 text-caption font-semibold text-white shadow"
            data-testid="map-badge">{badge}</span>
        )}
        {view === "map" && mapStatus === "loading" &&
          overlay(<p className="flex items-center gap-2 text-small text-fg-secondary"><Loader2 className="size-4 animate-spin" aria-hidden />{T.loading[lang]}</p>)}
        {view === "streetview" && !streetView && overlay(
          <div className="space-y-2">
            <EyeOff className="mx-auto size-6 text-fg-muted" aria-hidden />
            <p className="text-body font-medium">{T.svOff[lang]}</p>
            <button type="button" onClick={() => setView("map")} className="text-small font-medium text-brand hover:underline">{T.backToMap[lang]}</button>
          </div>, "note", "streetview-off")}
        {view === "streetview" && streetView && (sv === "idle" || sv === "checking") &&
          overlay(<p className="flex items-center gap-2 text-small text-fg-secondary"><Loader2 className="size-4 animate-spin" aria-hidden />{T.checking[lang]}</p>)}
        {view === "streetview" && (sv === "unavailable" || sv === "error") && overlay(
          <div className="space-y-2">
            <EyeOff className="mx-auto size-6 text-fg-muted" aria-hidden />
            <p className="text-body font-medium">{sv === "unavailable" ? T.noImagery[lang] : T.svError[lang]}</p>
            <button type="button" onClick={() => setView("map")} className="text-small font-medium text-brand hover:underline">{T.backToMap[lang]}</button>
          </div>, "note", sv === "unavailable" ? "streetview-unavailable" : "streetview-error")}
      </div>
    </div>
  );
}
