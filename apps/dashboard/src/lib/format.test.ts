import { describe, expect, it } from "vitest";
import { formatMoney, formatPercent, formatRelative } from "./format";
import { humanize, toneFor } from "./status";

describe("formatMoney", () => {
  it("formats decimal strings exactly, without floating point", () => {
    expect(formatMoney("1250000")).toBe("SAR 1,250,000");
    expect(formatMoney("1250000.5", { decimals: 2 })).toBe("SAR 1,250,000.50");
    expect(formatMoney("9007199254740993.99", { decimals: 2 })).toBe("SAR 9,007,199,254,740,993.99");
  });
  it("rounds half up, carrying into the integer part", () => {
    expect(formatMoney("0.995", { decimals: 2 })).toBe("SAR 1.00");
    expect(formatMoney("1999.5")).toBe("SAR 2,000");
  });
  it("handles negatives and invalid values", () => {
    expect(formatMoney("-84500.00", { decimals: 2 })).toBe("−SAR 84,500.00");
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney("abc")).toBe("—");
  });
});

describe("other formatters", () => {
  it("percent and relative time", () => {
    expect(formatPercent(82.44)).toBe("82.4%");
    const now = new Date("2026-11-16T12:00:00Z");
    expect(formatRelative("2026-11-16T11:59:40Z", now)).toBe("just now");
    expect(formatRelative("2026-11-16T09:00:00Z", now)).toBe("3 h ago");
    expect(formatRelative("2026-11-16T12:30:00Z", now)).toBe("in 30 min");
    expect(formatRelative("2026-11-18T12:00:00Z", now)).toBe("in 2 d");
    expect(formatRelative("2026-11-16T12:00:30Z", now)).toBe("just now");
  });
  it("status tones are consistent", () => {
    expect(toneFor("pending_approval")).toBe("warning");
    expect(toneFor("approved")).toBe("success");
    expect(toneFor("unknown-status")).toBe("neutral");
    expect(humanize("pending_approval")).toBe("Pending approval");
  });
});
