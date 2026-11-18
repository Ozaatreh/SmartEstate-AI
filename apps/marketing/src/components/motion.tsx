import * as React from "react";
import { cn } from "@/lib/utils";

/** True when the visitor asked the OS to reduce motion. */
export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Adds `.is-visible` once the element first enters the viewport (then stops observing, so it never replays when the
 * visitor scrolls back). Without IntersectionObserver, or with reduced motion, content is visible immediately.
 */
export function useRevealOnce<T extends HTMLElement>() {
  const ref = React.useRef<T>(null);
  const [visible, setVisible] = React.useState(() => typeof IntersectionObserver === "undefined" || prefersReducedMotion());
  React.useEffect(() => {
    const el = ref.current;
    if (visible || !el) return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setVisible(true); io.disconnect(); }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    io.observe(el);
    return () => io.disconnect();
  }, [visible]);
  return { ref, visible };
}

type RevealVariant = "up" | "fade" | "image";
const VARIANT: Record<RevealVariant, string> = { up: "reveal", fade: "reveal-fade", image: "reveal-image" };

/** Scroll-reveal wrapper: fade-up (default), fade, or image clip reveal; `delay` (ms) staggers siblings. */
export function Reveal({ as: Tag = "div", variant = "up", delay = 0, className, style, children, ...rest }: {
  as?: React.ElementType; variant?: RevealVariant; delay?: number; className?: string; style?: React.CSSProperties; children?: React.ReactNode;
} & Omit<React.HTMLAttributes<HTMLElement>, "style" | "className">) {
  const { ref, visible } = useRevealOnce<HTMLElement>();
  return (
    <Tag ref={ref} className={cn(VARIANT[variant], visible && "is-visible", className)}
      style={{ ...style, "--d": `${delay}ms` } as React.CSSProperties} {...rest}>
      {children}
    </Tag>
  );
}

/**
 * Very subtle scroll parallax: moves the element by up to `strength` px (transform only, one rAF per scroll frame,
 * only while it is on screen). Off with reduced motion.
 */
export function useParallax<T extends HTMLElement>(strength = 24) {
  const ref = React.useRef<T>(null);
  React.useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      if (r.bottom < 0 || r.top > vh) return;
      const progress = (r.top + r.height / 2 - vh / 2) / vh; // -1…1 around the viewport centre
      el.style.transform = `translate3d(0, ${(-progress * strength).toFixed(1)}px, 0) scale(1.06)`;
    };
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); };
  }, [strength]);
  return ref;
}

/** Splits a headline into words that rise in one after another (screen readers get the whole sentence). */
export function StaggerWords({ text, start = 0, step = 70 }: { text: string; start?: number; step?: number }) {
  const words = text.split(" ");
  return (
    <>
      <span className="sr-only">{text}</span>
      <span aria-hidden>
        {words.map((w, i) => (
          <React.Fragment key={`${w}-${i}`}>
            <span className="inline-block overflow-hidden pb-[0.08em] align-bottom">
              <span className="enter-up inline-block" style={{ "--d": `${start + i * step}ms` } as React.CSSProperties}>{w}</span>
            </span>
            {i < words.length - 1 && " "}
          </React.Fragment>
        ))}
      </span>
    </>
  );
}
