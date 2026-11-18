import * as React from "react";

export type Theme = "light" | "dark";
export const THEME_KEY = "smartestate-theme";
const COLORS: Record<Theme, string> = { light: "#F7F6F3", dark: "#191B1E" };

function stored(): Theme | null {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

function system(): Theme {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** The theme in effect: a saved choice, otherwise the system preference (index.html applies it before first paint). */
export function currentTheme(): Theme {
  return stored() ?? system();
}

export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", COLORS[theme]);
}

/** Light/dark theme: follows the system until the visitor chooses, then the choice is remembered (localStorage). */
export function useTheme() {
  const [theme, setThemeState] = React.useState<Theme>(currentTheme);

  React.useEffect(() => { applyTheme(theme); }, [theme]);

  // Without a saved choice, keep following the operating system's setting.
  React.useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => { if (!stored()) setThemeState(system()); };
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);

  const setTheme = React.useCallback((t: Theme) => {
    try { localStorage.setItem(THEME_KEY, t); } catch { /* private mode: the choice lasts for this page only */ }
    setThemeState(t);
  }, []);

  return { theme, setTheme, toggle: () => setTheme(theme === "dark" ? "light" : "dark") };
}
