import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("keeps colour classes next to custom font-size classes", () => {
    expect(cn("text-primary-foreground", "text-body")).toBe("text-primary-foreground text-body");
    expect(cn("text-small", "text-body")).toBe("text-body");
  });
});
