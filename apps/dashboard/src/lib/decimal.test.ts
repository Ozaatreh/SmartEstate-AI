import { describe, expect, it } from "vitest";
import { compareMoney, lineTotal, subtractMoney, sumMoney } from "./decimal";

describe("decimal", () => {
  it("multiplies quantity × price exactly with half-up rounding (matches the server)", () => {
    expect(lineTotal("3.333", "0.15")).toBe("0.50");
    expect(lineTotal("2", "1999.99")).toBe("3999.98");
    expect(lineTotal("0.005", "1.00")).toBe("0.01");
    expect(lineTotal("120", "185.00")).toBe("22200.00");
    expect(lineTotal("1", "9999999999999999.99")).toBe("9999999999999999.99");
  });
  it("rejects malformed input instead of guessing", () => {
    expect(lineTotal("1.2345", "1.00")).toBeNull();
    expect(lineTotal("abc", "1.00")).toBeNull();
    expect(lineTotal("1", "1.001")).toBeNull();
  });
  it("sums and compares money strings without floats", () => {
    expect(sumMoney(["0.10", "0.20", null, "0.30"])).toBe("0.60");
    expect(subtractMoney("100.00", "160.50")).toBe("-60.50");
    expect(compareMoney("0.30", sumMoney(["0.10", "0.20"]))).toBe(0);
    expect(compareMoney("1.00", "2.00")).toBe(-1);
  });
});
