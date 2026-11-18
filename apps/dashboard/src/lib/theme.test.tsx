import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ThemeToggle } from "@/components/layout/topbar";
import { TooltipProvider } from "@/components/ui/primitives";

describe("theme", () => {
  it("switches the whole app between light and dark and remembers the choice", async () => {
    localStorage.removeItem("smartestate-theme");
    document.documentElement.classList.remove("dark");
    render(<TooltipProvider><ThemeToggle /></TooltipProvider>);
    await userEvent.click(screen.getByRole("button", { name: "Switch to dark theme" })); // jsdom's system preference is light
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("smartestate-theme")).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem("smartestate-theme")).toBe("light");
  });
});
