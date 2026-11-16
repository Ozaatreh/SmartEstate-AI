/**
 * Exact decimal arithmetic for form previews (quantity × unit price, sums), using BigInt fixed-point.
 * The server is the authority; this only mirrors its rounding (half-up to cents) for live totals.
 */

const SCALE = 5n; // 3 quantity decimals + 2 price decimals

function parse(value: string, decimals: number): bigint | null {
  const v = value.trim();
  if (!/^\d+(\.\d+)?$/.test(v)) return null;
  const [i = "0", f = ""] = v.split(".");
  if (f.length > decimals) return null;
  return BigInt(i + f.padEnd(decimals, "0"));
}

/** "3.333" × "0.15" → "0.50" (or null when an input isn't a valid decimal). */
export function lineTotal(quantity: string, unitPrice: string): string | null {
  const q = parse(quantity, 3);
  const p = parse(unitPrice, 2);
  if (q === null || p === null) return null;
  const raw = q * p; // scale 10^5
  const cents = (raw + 500n) / 1000n; // half-up to scale 10^2
  return fromCents(cents);
}

export function sumMoney(values: (string | null | undefined)[]): string {
  let cents = 0n;
  for (const v of values) {
    const c = v ? parse(v, 2) : null;
    if (c !== null) cents += c;
  }
  return fromCents(cents);
}

/** Signed difference a − b of two money strings. */
export function subtractMoney(a: string, b: string): string {
  const neg = (s: string) => s.trim().startsWith("-");
  const abs = (s: string) => parse(s.replace("-", ""), 2) ?? 0n;
  const ca = (neg(a) ? -1n : 1n) * abs(a);
  const cb = (neg(b) ? -1n : 1n) * abs(b);
  return fromCents(ca - cb);
}

export function compareMoney(a: string, b: string): number {
  const d = subtractMoney(a, b);
  return d.startsWith("-") ? -1 : d === "0.00" ? 0 : 1;
}

function fromCents(cents: bigint): string {
  const neg = cents < 0n;
  const abs = neg ? -cents : cents;
  const s = abs.toString().padStart(3, "0");
  return `${neg ? "-" : ""}${s.slice(0, -2)}.${s.slice(-2)}`;
}

export const _internal = { SCALE };
