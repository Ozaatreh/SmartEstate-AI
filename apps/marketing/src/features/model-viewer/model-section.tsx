import { Box, Info, Play } from "lucide-react";
import * as React from "react";
import { Skeleton } from "@/components/ui";
import type { PublicModel } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const ModelViewer = React.lazy(() => import("./model-viewer"));

type T2 = { en: string; ar: string };
const REPRESENTATION: Record<string, { label: T2; note: T2 }> = {
  design: {
    label: { en: "Architectural design model", ar: "نموذج التصميم المعماري" },
    note: { en: "Based on the design drawings; the finished building may differ.", ar: "مبني على المخططات التصميمية، وقد يختلف المبنى المنفّذ." },
  },
  as_built: { label: { en: "As-built model", ar: "نموذج المبنى المنفّذ" }, note: { en: "Captured from the finished building.", ar: "مأخوذ من المبنى بعد اكتماله." } },
  illustrative: {
    label: { en: "Illustrative model", ar: "نموذج توضيحي" },
    note: { en: "Indicative only — not an exact representation of the property.", ar: "للاسترشاد فقط — ليس تمثيلاً دقيقاً للعقار." },
  },
};

const size = (n: number) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);

/**
 * "3D model" section for a project or unit page: approved models with their labels and credits. Renders nothing when
 * there are none (the old "A 3D model isn't available yet" placeholder was removed: projects can have the interactive
 * showcase instead, and unit pages simply omit the section).
 */
export function ModelSection({ models, isDemo, heading = "3D model" }: {
  models: PublicModel[]; isDemo: boolean; heading?: string;
  /** Kept for callers; the enquiry link lived in the removed empty state. */
  enquireHref?: string;
}) {
  const { t, lang } = useI18n();
  const [selected, setSelected] = React.useState(0);
  const [opened, setOpened] = React.useState<string | null>(null);
  const m = models[Math.min(selected, models.length - 1)];
  if (!m) return null;
  const rep = REPRESENTATION[m.representation] ?? REPRESENTATION.illustrative!;

  return (
    <section aria-labelledby="model-heading" className="rounded-[var(--radius-panel)] border border-border bg-surface p-5">
      <h2 id="model-heading" className="flex items-center gap-2 text-h3 font-semibold"><Box className="size-5 text-brand" aria-hidden />{heading}</h2>
          {models.length > 1 && (
            <div className="mt-3 flex flex-wrap gap-2" role="tablist" aria-label={t("Models", "النماذج")}>
              {models.map((x, i) => (
                <button key={x.id} type="button" role="tab" aria-selected={i === selected} onClick={() => setSelected(i)}
                  className={cn("h-8 rounded-full border px-3 text-small transition-colors",
                    i === selected ? "border-brand bg-brand-subtle text-brand" : "border-border text-fg-secondary hover:border-border-strong")}>
                  {x.title}
                </button>
              ))}
            </div>
          )}
          <div className="mt-4">
            {opened === m.id ? (
              <React.Suspense fallback={<Skeleton className="aspect-[4/3] w-full sm:aspect-video" />}>
                <ModelViewer key={m.id} url={m.file_url} title={m.title} />
              </React.Suspense>
            ) : (
              <button type="button" onClick={() => setOpened(m.id)}
                className="grid aspect-[4/3] w-full place-items-center rounded-[var(--radius-control)] border border-border bg-surface-sunken text-center transition-colors hover:bg-border-subtle sm:aspect-video">
                <span className="space-y-2">
                  <Play className="mx-auto size-8 text-brand" aria-hidden />
                  <span className="block text-body font-medium">{t("View the 3D model", "عرض النموذج ثلاثي الأبعاد")}</span>
                  <span className="block text-caption text-fg-muted">{m.format.toUpperCase()} · {size(m.size_bytes)}</span>
                </span>
              </button>
            )}
          </div>
          <div className="mt-3 space-y-1 text-small">
            <p><span className="font-medium">{m.title}</span>{m.unit_code ? ` · ${t("Unit", "الوحدة")} ${m.unit_code}` : ""}</p>
            {m.caption && <p className="text-fg-secondary">{m.caption}</p>}
            <p className="flex items-start gap-1.5 text-fg-secondary"><Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <span><span className="font-medium text-fg">{rep.label[lang]}.</span> {rep.note[lang]}</span></p>
            {isDemo && <p className="text-fg-secondary">{t("Fictional demo project — this model does not depict a real building.", "مشروع تجريبي وهمي — هذا النموذج لا يمثّل مبنى حقيقياً.")}</p>}
            <p className="text-caption text-fg-muted">{t("Model:", "النموذج:")} {m.credit}</p>
          </div>
    </section>
  );
}
