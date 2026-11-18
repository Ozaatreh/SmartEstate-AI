import { AlertTriangle, Loader2, Maximize2, Minimize2, MonitorX, Move3d, RotateCcw } from "lucide-react";
import * as React from "react";
import { hasWebGL } from "@/features/model-viewer/webgl";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { SceneHandle } from "./property-scene";
import type { ViewerCamera } from "./showcases";

const PropertyScene = React.lazy(() => import("./property-scene"));

type Status = "loading" | "ready" | "error" | "unsupported";

export interface InteractivePropertyViewerProps {
  /** Same-origin GLB under `public/`. */
  modelUrl: string;
  /** Still image of the model, shown while loading and as the no-WebGL fallback. */
  posterUrl?: string;
  /** Accessible name, e.g. "NOVA Residences". */
  title: string;
  camera: ViewerCamera;
  className?: string;
}

class SceneBoundary extends React.Component<{ onError: () => void; children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onError(); }
  render() { return this.state.failed ? null : this.props.children; }
}

/** Starts loading the 3D chunk only once the viewer is within ~one screen of the viewport. */
function useNearViewport(ref: React.RefObject<HTMLElement | null>) {
  const [near, setNear] = React.useState(() => typeof IntersectionObserver === "undefined");
  React.useEffect(() => {
    const el = ref.current;
    if (near || !el) return;
    const io = new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting)) setNear(true); }, { rootMargin: "400px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, near]);
  return near;
}

/**
 * Interactive 360° property viewer (React Three Fiber + Drei). The model stays still; the camera orbits it.
 * Drag / one finger to rotate, scroll / pinch to zoom, with damping; reset and fullscreen buttons; loading, error and
 * no-WebGL states. three.js is lazy-loaded when the viewer approaches the viewport.
 */
export function InteractivePropertyViewer({ modelUrl, posterUrl, title, camera, className }: InteractivePropertyViewerProps) {
  const frame = React.useRef<HTMLDivElement>(null);
  const { t } = useI18n();
  const scene = React.useRef<SceneHandle | null>(null);
  const near = useNearViewport(frame);
  const [webgl] = React.useState(hasWebGL);
  const [touch] = React.useState(() => typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches);
  const [status, setStatus] = React.useState<Status>(webgl ? "loading" : "unsupported");
  const [progress, setProgress] = React.useState(0);
  const [attempt, setAttempt] = React.useState(0);
  const [fullscreen, setFullscreen] = React.useState(false);
  /** Browsers without the Fullscreen API on elements (iPhone Safari) get a fixed full-window overlay instead. */
  const [overlay, setOverlay] = React.useState(false);

  React.useEffect(() => {
    const sync = () => {
      const on = document.fullscreenElement === frame.current;
      setFullscreen(on);
      if (on) setOverlay(false);
    };
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  React.useEffect(() => {
    if (!overlay) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOverlay(false); };
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => { document.body.style.overflow = prev; window.removeEventListener("keydown", onKey); };
  }, [overlay]);

  const onLoaded = React.useCallback(() => setStatus("ready"), []);
  const onError = React.useCallback(() => setStatus("error"), []);
  const retry = async () => {
    try { (await import("@react-three/drei")).useGLTF.clear(modelUrl); } catch { /* the chunk itself failed: just retry */ }
    setProgress(0);
    setStatus("loading");
    setAttempt((n) => n + 1);
  };
  const toggleFullscreen = () => {
    const el = frame.current;
    if (!el) return;
    if (overlay) return setOverlay(false);
    if (document.fullscreenElement) return void document.exitFullscreen();
    if (typeof el.requestFullscreen !== "function") return setOverlay(true);
    // Some embedded browsers neither enter fullscreen nor reject the request: fall back to the overlay after a moment.
    const fallback = window.setTimeout(() => { if (document.fullscreenElement !== el) setOverlay(true); }, 800);
    void el.requestFullscreen().catch(() => { window.clearTimeout(fallback); setOverlay(true); });
  };
  const expanded = fullscreen || overlay;
  const label = t(`Interactive 3D model: ${title}. Drag to rotate, scroll or pinch to zoom.`, `نموذج تفاعلي ثلاثي الأبعاد: ${title}. اسحب للتدوير، ومرّر أو باعد بإصبعين للتكبير.`);
  const mounted = near && (status === "loading" || status === "ready");

  return (
    <div ref={frame} data-testid="property-viewer" data-status={status}
      className={cn("relative isolate overflow-hidden bg-[#121316] text-white",
        "bg-[radial-gradient(ellipse_at_50%_35%,#30333a_0%,#1a1c20_45%,#0e0f11_100%)]",
        expanded ? "h-full w-full" : "h-[380px] rounded-[20px] sm:h-[480px] lg:h-[600px]",
        overlay ? "overlay-in fixed inset-0 z-50 m-0 h-[100dvh] rounded-none" : className)}>
      {posterUrl && status !== "ready" && (
        <img src={posterUrl} alt={status === "unsupported" ? t(`Still image of the 3D model: ${title}`, `صورة ثابتة للنموذج ثلاثي الأبعاد: ${title}`) : ""} aria-hidden={status !== "unsupported"}
          className={cn("absolute inset-0 size-full object-cover transition-opacity duration-700", status === "unsupported" ? "opacity-60" : "opacity-25")}
          loading="lazy" decoding="async" />
      )}

      {mounted && (
        <div className={cn("absolute inset-0 transition-[opacity,transform] duration-[1200ms] ease-[var(--ease-out-soft)] motion-reduce:transition-none",
          status === "ready" ? "scale-100 opacity-100" : "scale-[1.03] opacity-0")}>
          <SceneBoundary key={attempt} onError={onError}>
            <React.Suspense fallback={null}>
              <PropertyScene url={modelUrl} label={label} camera={camera} handle={scene} onProgress={setProgress} onLoaded={onLoaded} />
            </React.Suspense>
          </SceneBoundary>
        </div>
      )}

      {status === "loading" && (
        <div className="absolute inset-0 grid place-items-center" role="status" data-testid="viewer-loading">
          <div className="enter-fade flex flex-col items-center gap-3 text-center">
            <Loader2 className="size-7 animate-spin text-white/80" aria-hidden />
            <p className="text-small tracking-wide text-white/80">{t("Loading 3D model", "جارٍ تحميل النموذج ثلاثي الأبعاد")}{progress > 0 ? ` · ${progress}%` : "…"}</p>
            <div className="h-0.5 w-40 overflow-hidden rounded-full bg-white/15" aria-hidden>
              <div className="h-full origin-left bg-[#d39a72] transition-transform duration-500 ease-[var(--ease-out-soft)] rtl:origin-right" style={{ transform: `scaleX(${progress / 100})` }} />
            </div>
          </div>
        </div>
      )}

      {status === "error" && (
        <div className="absolute inset-0 grid place-items-center bg-black/40 p-6 text-center" role="alert" data-testid="viewer-error">
          <div className="max-w-sm space-y-2">
            <AlertTriangle className="mx-auto size-7 text-amber-300" aria-hidden />
            <p className="text-body font-medium">{t("The 3D model couldn't be loaded.", "تعذّر تحميل النموذج ثلاثي الأبعاد.")}</p>
            <p className="text-small text-white/70">{t("Check your connection and try again.", "تحقق من اتصالك وحاول مجدداً.")}</p>
            <button type="button" onClick={() => void retry()}
              className="mt-2 rounded-full border border-white/30 px-4 py-1.5 text-small font-medium transition-colors hover:bg-white/10">{t("Try again", "حاول مجدداً")}</button>
          </div>
        </div>
      )}

      {status === "unsupported" && (
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent p-6 pt-16" role="note" data-testid="viewer-unsupported">
          <p className="flex items-center gap-2 text-body font-medium"><MonitorX className="size-5 shrink-0" aria-hidden />{t("Interactive 3D isn't available on this device.", "العرض التفاعلي ثلاثي الأبعاد غير متاح على هذا الجهاز.")}</p>
          <p className="mt-1 text-small text-white/75">{t("Your browser doesn't support WebGL, so a still image is shown instead. Try a recent version of Chrome, Edge, Safari or Firefox.", "متصفحك لا يدعم WebGL، لذلك تُعرض صورة ثابتة بدلاً منه. جرّب إصداراً حديثاً من Chrome أو Edge أو Safari أو Firefox.")}</p>
        </div>
      )}

      {status === "ready" && (
        <>
          <p style={{ "--d": "600ms" } as React.CSSProperties} className="enter-fade pointer-events-none absolute bottom-4 start-4 flex items-center gap-1.5 text-caption tracking-wide text-white/70 sm:start-5" data-testid="viewer-hint">
            <Move3d className="size-3.5" aria-hidden /> {touch ? t("Drag to rotate · Pinch to zoom", "اسحب للتدوير · باعد بإصبعين للتكبير") : t("Drag to rotate · Scroll to zoom", "اسحب للتدوير · مرّر للتكبير")}
          </p>
          <div style={{ "--d": "500ms" } as React.CSSProperties} className="enter-up absolute bottom-3 end-3 flex gap-2 sm:end-4" role="toolbar" aria-label={t("3D view controls", "عناصر التحكم بالعرض ثلاثي الأبعاد")}>
            <ViewerButton label={t("Reset camera", "إعادة ضبط الكاميرا")} onClick={() => scene.current?.reset()}><RotateCcw /></ViewerButton>
            <ViewerButton label={expanded ? t("Exit fullscreen", "الخروج من ملء الشاشة") : t("Fullscreen", "ملء الشاشة")} onClick={toggleFullscreen}>
              {expanded ? <Minimize2 /> : <Maximize2 />}
            </ViewerButton>
          </div>
        </>
      )}
    </div>
  );
}

function ViewerButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} title={label}
      className="press group/btn grid size-10 place-items-center rounded-full border border-white/10 bg-white/10 text-white backdrop-blur-md transition-[background-color,border-color,transform] duration-300 hover:-translate-y-0.5 hover:border-white/30 hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 [&_svg]:size-4 [&_svg]:transition-transform [&_svg]:duration-500 hover:[&_svg]:scale-110">
      {children}
    </button>
  );
}
