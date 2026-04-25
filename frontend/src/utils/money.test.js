import { describe, it, expect } from "vitest";
import {
  parseMoneyToCents,
  centsToApiString,
  splitInclusiveGrossKenya16,
  divHalfUpPositive,
  mulCentsByQty,
} from "./money";
import { pricingService } from "../services/pricingService";

describe("parseMoneyToCents / centsToApiString", () => {
  it("parses KES 500.00 without drift", () => {
    expect(parseMoneyToCents("500.00")).toBe(50000);
    expect(parseMoneyToCents(500)).toBe(50000);
    expect(centsToApiString(50000)).toBe("500.00");
  });
});

describe("splitInclusiveGrossKenya16", () => {
  it("splits 500.00 gross at 16%", () => {
    const { netCents, vatCents } = splitInclusiveGrossKenya16(50000);
    expect(netCents).toBe(43103);
    expect(vatCents).toBe(6897);
    expect(netCents + vatCents).toBe(50000);
  });
});

describe("divHalfUpPositive", () => {
  it("rounds 0.5 up", () => {
    expect(divHalfUpPositive(5, 10)).toBe(1);
    expect(divHalfUpPositive(4, 10)).toBe(0);
  });
});

describe("pricingService.calculateTotals VAT-inclusive", () => {
  it("single taxable line KES 500 stays 500.00 total", () => {
    const cart = [
      {
        id: 1,
        selling_price: "500.00",
        qty: 1,
        discount: "0.00",
        vat_exempt: false,
        tax_code: "B",
      },
    ];
    const t = pricingService.calculateTotals(cart);
    expect(t.totalCents).toBe(50000);
    expect(t.total).toBe(500);
    expect(centsToApiString(t.totalCents)).toBe("500.00");
    expect(t.subtotalExclusiveCents + t.vatAmountCents).toBe(50000);
  });

  it("line extension uses integer cents", () => {
    const cart = [
      {
        id: 1,
        selling_price: "250.00",
        qty: 2,
        discount: "0.00",
        vat_exempt: false,
        tax_code: "B",
      },
    ];
    const t = pricingService.calculateTotals(cart);
    expect(mulCentsByQty(25000, 2)).toBe(50000);
    expect(t.totalCents).toBe(50000);
  });
});
