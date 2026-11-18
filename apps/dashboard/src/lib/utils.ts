import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * tailwind-merge must know the custom type scale (text-body, text-small, …); otherwise it treats
 * them as text *colours* and drops real colour classes such as text-primary-foreground.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["caption", "small", "body", "lead", "h3", "h2", "h1", "display"] }],
    },
  },
});

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** "Layla Haddad" → "LH" */
export function initialsOf(name: string): string {
  return name.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase() || "?";
}
