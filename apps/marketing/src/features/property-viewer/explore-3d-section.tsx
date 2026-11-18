import { ArrowRight, Info } from "lucide-react";
import { Link } from "react-router-dom";
import { InteractivePropertyViewer } from "./interactive-property-viewer";
import { useI18n } from "@/lib/i18n";
import type { Showcase } from "./showcases";

export interface ExploreLink { label: string; href: string }

/** "Explore in 3D" band on a project page: the interactive viewer as the centrepiece, its notice, and page links. */
export function Explore3DSection({ projectName, showcase, links }: { projectName: string; showcase: Showcase; links: ExploreLink[] }) {
  const short = projectName.split(" ")[0] ?? projectName;
  const { t, lang } = useI18n();
  return (
    <section aria-labelledby="explore-3d-heading" data-testid="explore-3d"
      className="-mx-4 mt-8 bg-[#0e0f11] px-4 py-10 text-white sm:mx-0 sm:rounded-[28px] sm:px-8 sm:py-12 lg:px-12">
      <div className="max-w-2xl">
        <p className="text-caption font-semibold uppercase tracking-[0.2em] text-white/55">{t("Explore in 3D", "استكشف بتقنية ثلاثية الأبعاد")}</p>
        <h2 id="explore-3d-heading" className="mt-3 font-display text-[30px] font-semibold leading-tight tracking-[-0.02em] sm:text-[40px]">
          {t(`Experience ${short} from Every Angle.`, `اكتشف ${short} من كل زاوية.`)}
        </h2>
        <p className="mt-3 text-lead text-white/70">
          {t(`Discover the architecture and design of ${short} through an interactive 360-degree experience.`, `اكتشف عمارة ${short} وتصميمه من خلال تجربة تفاعلية بزاوية 360 درجة.`)}
        </p>
      </div>

      <InteractivePropertyViewer className="mt-8" modelUrl={showcase.modelUrl} posterUrl={showcase.posterUrl} title={projectName} camera={showcase.camera} />

      <p className="mt-4 flex items-start gap-2 text-small text-white/65" data-testid="explore-3d-notice">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />{showcase.notice[lang]}
      </p>

      {links.length > 0 && (
        <nav aria-label={t(`More about ${projectName}`, `المزيد عن ${projectName}`)} className="mt-8 flex flex-wrap gap-x-8 gap-y-3 border-t border-white/10 pt-6">
          {links.map((l) => {
            const cls = "group inline-flex items-center gap-1.5 text-body font-medium text-white/85 transition-colors hover:text-white";
            const body = <>{l.label}<ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5" aria-hidden /></>;
            return l.href.startsWith("#")
              ? <a key={l.label} href={l.href} className={cls}>{body}</a>
              : <Link key={l.label} to={l.href} className={cls}>{body}</Link>;
          })}
        </nav>
      )}
    </section>
  );
}
