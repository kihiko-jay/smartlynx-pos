/**
 * POS money helpers — integer cents + half-up integer division (no float drift for KES).
 * VAT split matches backend policy: 16% inclusive → net = round_half_up(gross×100/116), vat = gross − net.
 */

export const VAT_NUMERATOR = 16;
export const VAT_DENOMINATOR = 100;
const SPLIT_DENOM = VAT_DENOMINATOR + VAT_NUMERATOR; // 116

/**
 * Round-half-up for non-negative integers: floor((a + b/2) / b) with even b.
 * @param {number} a
 * @param {number} b
 */
export function divHalfUpPositive(a, b) {
  if (a < 0 || b <= 0) throw new RangeError("divHalfUpPositive expects a >= 0 and b > 0");
  const q = Math.floor(a / b);
  const r = a % b;
  return 2 * r >= b ? q + 1 : q;
}

/**
 * Parse money-like input to integer cents (KES minor units). No binary-float paths for typical 2dp inputs.
 * @param {string|number|null|undefined} value
 * @returns {number}
 */
export function parseMoneyToCents(value) {
  if (value == null || value === "") return 0;
  const s0 = String(value).trim().replace(/,/g, "");
  if (!s0 || s0 === ".") return 0;
  const neg = s0.startsWith("-");
  const s = neg ? s0.slice(1) : s0;
  if (!/^\d*(\.\d*)?$/.test(s)) return 0;
  const [intPartRaw, fracRaw = ""] = s.split(".");
  const intPart = intPartRaw === "" ? "0" : intPartRaw;
  const frac2 = (fracRaw + "00").slice(0, 2);
  const whole = intPart.replace(/^0+(?=\d)/, "") || "0";
  const cents = Number(whole) * 100 + Number(frac2);
  if (!Number.isFinite(cents) || !Number.isInteger(cents)) return 0;
  if (!Number.isSafeInteger(cents)) return neg ? -Number.MAX_SAFE_INTEGER : Number.MAX_SAFE_INTEGER;
  return neg ? -cents : cents;
}

/**
 * @param {number} cents
 * @returns {string} e.g. "500.00"
 */
export function centsToApiString(cents) {
  const neg = cents < 0;
  const a = Math.abs(cents);
  const whole = Math.floor(a / 100);
  const frac = String(a % 100).padStart(2, "0");
  return `${neg ? "-" : ""}${whole}.${frac}`;
}

/**
 * Stable display number for 2dp values (parse from our own decimal string).
 * @param {number} cents
 */
export function centsToDisplayNumber(cents) {
  return parseFloat(centsToApiString(cents));
}

/**
 * @param {number} unitCents
 * @param {number} qty
 */
export function mulCentsByQty(unitCents, qty) {
  const q = Number(qty);
  if (!Number.isFinite(q) || q <= 0 || !Number.isInteger(q)) return 0;
  const p = unitCents * q;
  if (!Number.isSafeInteger(p)) return Math.round(p);
  return p;
}

export function addCents(a, b) {
  return a + b;
}

export function subCents(a, b) {
  return a - b;
}

/**
 * Split VAT-inclusive gross (cents) into net + VAT at Kenya 16%.
 * @param {number} grossCents
 */
export function splitInclusiveGrossKenya16(grossCents) {
  if (grossCents <= 0) return { netCents: grossCents, vatCents: 0 };
  const netCents = divHalfUpPositive(grossCents * VAT_DENOMINATOR, SPLIT_DENOM);
  const vatCents = subCents(grossCents, netCents);
  return { netCents, vatCents };
}

/**
 * VAT on VAT-exclusive net (cents), Kenya 16%.
 * @param {number} netCents
 */
export function vatOnExclusiveNetKenya16(netCents) {
  if (netCents <= 0) return 0;
  return divHalfUpPositive(netCents * VAT_NUMERATOR, VAT_DENOMINATOR);
}

/**
 * Cashier cash input: allow "", ".", "500", "500.5" → cents.
 * @param {string} raw
 */
export function parseCashInputToCents(raw) {
  if (raw == null) return 0;
  const t = String(raw).trim();
  if (t === "" || t === ".") return 0;
  return parseMoneyToCents(t);
}

/** Same formatting rules as fmtKES in api/client (KES + en-KE grouping). */
export function fmtKESCents(cents) {
  const n = centsToDisplayNumber(cents);
  const formatted = n.toLocaleString("en-KE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  return `KES ${formatted}`;
}
