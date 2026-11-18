import { AlertTriangle, Loader2, MonitorX, Move3d } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export type ViewerStatus = "loading" | "ready" | "error" | "unsupported";

/** Loading / error / unsupported states drawn over the 3D canvas (and a usage hint once ready). */
export function ViewerOverlay({ status, progress, onRetry }: { status: ViewerStatus; progress: number | null; onRetry: () => void }) {
  const { t } = useI18n();
  if (status === "ready") {
    return (
      <p className="pointer-events-none absolute start-3 top-3 flex items-center gap-1.5 rounded-full bg-surface/90 px-2.5 py-1 text-caption text-fg-secondary">
        <Move3d className="size-3.5" aria-hidden /> {t("Drag to rotate · scroll or pinch to zoom", "اسحب للتدوير · مرّر أو باعد بإصبعين للتكبير")}
      </p>
    );
  }
  return (
    <div className="absolute inset-0 grid place-items-center bg-surface-subtle/90 p-6 text-center" role={status === "loading" ? "status" : "alert"}>
      {status === "loading" && (
        <div className="space-y-2">
          <Loader2 className="mx-auto size-6 animate-spin text-brand" aria-hidden />
          <p className="text-small text-fg-secondary">{t("Loading 3D model", "جارٍ تحميل النموذج ثلاثي الأبعاد")}{progress != null ? ` · ${progress}%` : "…"}</p>
        </div>
      )}
      {status === "error" && (
        <div className="max-w-sm space-y-2">
          <AlertTriangle className="mx-auto size-6 text-warning" aria-hidden />
          <p className="text-body font-medium">{t("The 3D model couldn't be loaded.", "تعذّر تحميل النموذج ثلاثي الأبعاد.")}</p>
          <p className="text-small text-fg-secondary">{t("Check your connection and try again.", "تحقق من اتصالك وحاول مجدداً.")}</p>
          <button type="button" onClick={onRetry} className="mt-1 text-small font-medium text-brand hover:underline">{t("Try again", "حاول مجدداً")}</button>
        </div>
      )}
      {status === "unsupported" && (
        <div className="max-w-sm space-y-2">
          <MonitorX className="mx-auto size-6 text-fg-muted" aria-hidden />
          <p className="text-body font-medium">{t("3D isn't available on this device.", "العرض ثلاثي الأبعاد غير متاح على هذا الجهاز.")}</p>
          <p className="text-small text-fg-secondary">{t("Your browser doesn't support WebGL. Try a recent version of Chrome, Edge, Safari or Firefox.", "متصفحك لا يدعم WebGL. جرّب إصداراً حديثاً من Chrome أو Edge أو Safari أو Firefox.")}</p>
        </div>
      )}
    </div>
  );
}
