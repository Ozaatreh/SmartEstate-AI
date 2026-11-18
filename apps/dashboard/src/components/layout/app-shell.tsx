import * as React from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Wordmark } from "@/components/system/brand";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { DesktopSidebar, SidebarNav } from "./sidebar";
import { TopBar } from "./topbar";

const STORAGE_KEY = "se.sidebar.collapsed";
const DESKTOP_QUERY = "(min-width: 1280px)";

function readStored(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = React.useState(() => window.matchMedia(DESKTOP_QUERY).matches);
  React.useEffect(() => {
    const mq = window.matchMedia(DESKTOP_QUERY);
    const onChange = () => setIsDesktop(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return isDesktop;
}

/**
 * Desktop ≥1280: full sidebar, collapsible (remembered). Tablet 768–1279: icon rail by default
 * (expandable for the session). Mobile <768: off-canvas sheet from the top-bar menu button.
 */
export function AppShell() {
  const isDesktop = useIsDesktop();
  const [desktopCollapsed, setDesktopCollapsed] = React.useState(readStored);
  const [tabletExpanded, setTabletExpanded] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const location = useLocation();
  const collapsed = isDesktop ? desktopCollapsed : !tabletExpanded;

  const toggle = React.useCallback(() => {
    if (isDesktop) {
      setDesktopCollapsed((v) => {
        try {
          window.localStorage.setItem(STORAGE_KEY, v ? "0" : "1");
        } catch { /* storage unavailable: keep in memory */ }
        return !v;
      });
    } else {
      setTabletExpanded((v) => !v);
    }
  }, [isDesktop]);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (e.key !== "[" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  // Collapse the tablet overlay / mobile sheet after navigating.
  const [prevPath, setPrevPath] = React.useState(location.pathname);
  if (prevPath !== location.pathname) {
    setPrevPath(location.pathname);
    setMobileOpen(false);
    if (!isDesktop) setTabletExpanded(false);
  }

  return (
    <div className="flex min-h-dvh bg-canvas">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">Skip to content</a>
      <DesktopSidebar collapsed={collapsed} onToggle={toggle} />

      <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" title="Navigation" className="bg-surface-subtle">
          <div className="flex h-[var(--topbar-height)] items-center border-b border-border px-4">
            <NavLink to="/" onClick={() => setMobileOpen(false)}><Wordmark /></NavLink>
          </div>
          <SidebarNav collapsed={false} onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Dialog>

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenMobileNav={() => setMobileOpen(true)} />
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 outline-none sm:px-6 lg:px-8 lg:py-8">
          <div key={location.pathname} className="animate-in fade-in-0 duration-200">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
