import { ExternalLink, Info, MapPin, MapPinOff, Navigation } from "lucide-react";
import { Link } from "react-router-dom";
import { buttonClass } from "@/components/ui";
import type { PublicLocation } from "@/lib/api";
import { MapPanel } from "./map-panel";
import type { Lang } from "./maps";


const T = {
  heading: { en: "Location", ar: "الموقع" },
  directions: { en: "Get directions", ar: "الاتجاهات" },
  open: { en: "Open in Google Maps", ar: "افتح في خرائط Google" },
  coordinates: { en: "Coordinates", ar: "الإحداثيات" },
  noKey: {
    en: "The interactive map isn't available right now. Use the links to open the location in Google Maps.",
    ar: "الخريطة التفاعلية غير متاحة حالياً. استخدم الروابط لفتح الموقع في خرائط Google.",
  },
  demo: {
    en: "This is a fictional demo project, so it has no real address and no map pin. The district and city are illustrative.",
    ar: "هذا مشروع تجريبي وهمي، لذلك ليس له عنوان حقيقي ولا موقع على الخريطة. الحي والمدينة للتوضيح فقط.",
  },
  pending: {
    en: "The exact location hasn't been published yet. Ask our team for directions or book a viewing.",
    ar: "لم يُنشر الموقع الدقيق بعد. تواصل مع فريقنا للحصول على الاتجاهات أو احجز موعد زيارة.",
  },
  ask: { en: "Ask for directions", ar: "اطلب الاتجاهات" },
  illustrative: { en: "Illustrative Location — Not the Actual Property Location.", ar: "موقع توضيحي — ليس الموقع الفعلي للعقار." },
  illustrativeBadge: { en: "Illustrative location", ar: "موقع توضيحي" },
  illustrativeDemo: {
    en: (label: string) => `This is a fictional demo project with no real address. The pin marks ${label}, a reference point used for illustration only.`,
    ar: (label: string) => `هذا مشروع تجريبي وهمي بلا عنوان حقيقي. يشير الدبوس إلى ${label}، وهي نقطة مرجعية للتوضيح فقط.`,
  },
  illustrativeReal: {
    en: (label: string) => `The exact location hasn't been published yet. The pin marks ${label}, a nearby reference point used for illustration only.`,
    ar: (label: string) => `لم يُنشر الموقع الدقيق بعد. يشير الدبوس إلى ${label}، وهي نقطة مرجعية للتوضيح فقط.`,
  },
  refDirections: { en: (label: string) => `Directions to ${label} (reference point)`, ar: (label: string) => `الاتجاهات إلى ${label} (نقطة مرجعية)` },
  refOpen: { en: (label: string) => `Open ${label} in Google Maps`, ar: (label: string) => `افتح ${label} في خرائط Google` },
  refMapName: { en: (label: string) => `${label} (illustrative reference point)`, ar: (label: string) => `${label} (نقطة مرجعية توضيحية)` },
} as const;

// Long reference-point labels (and Arabic) must wrap on phones instead of widening the page.
const WRAP = "h-auto min-h-10 max-w-full shrink whitespace-normal py-2 text-start";

const inRange = (lat: number, lng: number) => Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180;

function validPoint(loc: PublicLocation): { lat: number; lng: number } | null {
  if (!loc.verified || loc.latitude == null || loc.longitude == null) return null;
  const lat = Number(loc.latitude), lng = Number(loc.longitude);
  return inRange(lat, lng) ? { lat, lng } : null;
}

/** The illustrative reference point, only for locations that aren't verified (a verified location always wins). */
function validReference(loc: PublicLocation): { lat: number; lng: number; label: string; directions: string | null; maps: string | null } | null {
  const r = loc.illustrative;
  if (loc.verified || !r || !r.label?.trim()) return null;
  const lat = Number(r.latitude), lng = Number(r.longitude);
  if (!inRange(lat, lng)) return null;
  return { lat, lng, label: r.label.trim(), directions: isGoogleMapsUrl(r.directions_url) ? r.directions_url : null, maps: isGoogleMapsUrl(r.maps_url) ? r.maps_url : null };
}

const isGoogleMapsUrl = (u: string | null): u is string => !!u && /^https:\/\/www\.google\.com\/maps\//.test(u);

export function ProjectLocation({ location: loc, projectName, projectCode, isDemo, lang = "en", apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY, mapId = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID,
  streetView = import.meta.env.VITE_GOOGLE_MAPS_STREET_VIEW === "enabled" }: {
  location: PublicLocation; projectName: string; projectCode: string; isDemo: boolean; lang?: Lang; apiKey?: string; mapId?: string; streetView?: boolean;
}) {
  const point = validPoint(loc);
  const ref = point ? null : validReference(loc);
  const place = [loc.district, loc.city, loc.country].filter(Boolean).join(lang === "ar" ? "، " : ", ");
  const key = apiKey?.trim();

  return (
    <section aria-labelledby="location-heading" lang={lang} dir={lang === "ar" ? "rtl" : "ltr"}
      className="rounded-[var(--radius-panel)] border border-border bg-surface p-5">
      <h2 id="location-heading" className="flex items-center gap-2 text-h3 font-semibold"><MapPin className="size-5 text-brand" aria-hidden />{T.heading[lang]}</h2>
      <p className="mt-1 text-body text-fg-secondary"><bdi>{place}</bdi></p>
      {point && loc.address && <p className="mt-0.5 text-small text-fg-muted"><bdi>{loc.address}</bdi></p>}

      {point ? (
        <>
          {key ? (
            <MapPanel lat={point.lat} lng={point.lng} apiKey={key} mapId={mapId?.trim() || "DEMO_MAP_ID"} lang={lang} projectName={projectName} streetView={streetView} />
          ) : (
            <p className="mt-4 rounded-[var(--radius-control)] border border-dashed border-border-strong bg-surface-subtle p-4 text-small text-fg-secondary" role="note" data-testid="map-nokey">
              {T.noKey[lang]}
              <span className="mt-1 block text-caption text-fg-muted" dir="ltr">{T.coordinates[lang]}: {point.lat}, {point.lng}</span>
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {isGoogleMapsUrl(loc.directions_url) && (
              <a href={loc.directions_url} target="_blank" rel="noopener noreferrer" className={buttonClass("brand", "md")}>
                <Navigation aria-hidden /> {T.directions[lang]}
              </a>
            )}
            {isGoogleMapsUrl(loc.maps_url) && (
              <a href={loc.maps_url} target="_blank" rel="noopener noreferrer" className={buttonClass("secondary", "md")}>
                <ExternalLink aria-hidden /> {T.open[lang]}
              </a>
            )}
          </div>
        </>
      ) : ref ? (
        <>
          <div className="mt-4 flex gap-3 rounded-[var(--radius-control)] border border-warning/40 bg-warning-subtle p-4" role="note" data-testid="illustrative-notice">
            <Info className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden />
            <div className="text-small text-fg-secondary">
              <p className="text-body font-semibold text-fg">{T.illustrative[lang]}</p>
              <p className="mt-1"><bdi>{(isDemo ? T.illustrativeDemo : T.illustrativeReal)[lang](ref.label)}</bdi></p>
            </div>
          </div>
          {key ? (
            <MapPanel lat={ref.lat} lng={ref.lng} apiKey={key} mapId={mapId?.trim() || "DEMO_MAP_ID"} lang={lang}
              projectName={T.refMapName[lang](ref.label)} streetView={streetView} badge={T.illustrativeBadge[lang]} />
          ) : (
            <p className="mt-4 rounded-[var(--radius-control)] border border-dashed border-border-strong bg-surface-subtle p-4 text-small text-fg-secondary" role="note" data-testid="map-nokey">
              {T.noKey[lang]}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {ref.directions && (
              <a href={ref.directions} target="_blank" rel="noopener noreferrer" className={buttonClass("secondary", "md", WRAP)}>
                <Navigation aria-hidden /> {T.refDirections[lang](ref.label)}
              </a>
            )}
            {ref.maps && (
              <a href={ref.maps} target="_blank" rel="noopener noreferrer" className={buttonClass("ghost", "md", WRAP)}>
                <ExternalLink aria-hidden /> {T.refOpen[lang](ref.label)}
              </a>
            )}
            {!isDemo && (
              <Link to={`/request-viewing?project=${encodeURIComponent(projectCode)}`} className={buttonClass("brand", "md")}>{T.ask[lang]}</Link>
            )}
          </div>
        </>
      ) : (
        <div className="mt-4 flex gap-3 rounded-[var(--radius-control)] border border-dashed border-border-strong bg-surface-subtle p-4" role="note" data-testid="map-fallback">
          <MapPinOff className="mt-0.5 size-5 shrink-0 text-fg-muted" aria-hidden />
          <div className="text-small text-fg-secondary">
            <p>{isDemo ? T.demo[lang] : T.pending[lang]}</p>
            {!isDemo && (
              <Link to={`/request-viewing?project=${encodeURIComponent(projectCode)}`} className="mt-2 inline-block font-medium text-brand hover:underline">{T.ask[lang]}</Link>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
