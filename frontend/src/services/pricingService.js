import { parseMoney } from "../api/client";

const VAT_RATE = 0.16;
const PRICES_INCLUDE_VAT = true;

// Utility to round money to 2 decimal places
const roundMoney = (value) => Math.round((Number(value) + Number.EPSILON) * 100) / 100;

export const pricingService = {
  // Check if item is VAT exempt
  getItemVatRate(item) {
    if (item.vat_exempt) return 0;
    if (["VAT_EXEMPT", "ZERO_RATED", "ZERO"].includes(item.tax_code)) return 0;
    return VAT_RATE;
  },

  // Get inclusive price (shelf price)
  getPriceInclusive(item) {
    return parseMoney(item.selling_price ?? item.price ?? 0);
  },

  // Get exclusive price (before VAT)
  getPriceExclusive(item) {
    const inclusive = this.getPriceInclusive(item);
    const rate = this.getItemVatRate(item);
    if (PRICES_INCLUDE_VAT && rate > 0) {
      return inclusive / (1 + rate);
    }
    return inclusive;
  },

  // Get display price (always inclusive for cart)
  getDisplayPrice(item) {
    return parseMoney(item.selling_price ?? item.price ?? 0);
  },

  // Calculate totals for cart
  calculateTotals(cart) {
    const grossSubtotalInclusive = roundMoney(
      cart.reduce((s, i) => s + this.getPriceInclusive(i) * i.qty, 0)
    );

    const vatAmount = roundMoney(
      cart.reduce((s, i) => {
        const inclusive = this.getPriceInclusive(i) * i.qty;
        const rate = this.getItemVatRate(i);
        if (PRICES_INCLUDE_VAT && rate > 0) {
          return s + (inclusive * rate) / (1 + rate);
        }
        return s + inclusive * rate;
      }, 0)
    );

    const subtotalExVat = roundMoney(
      PRICES_INCLUDE_VAT
        ? grossSubtotalInclusive - vatAmount
        : grossSubtotalInclusive
    );

    return {
      subtotalInclusive: roundMoney(grossSubtotalInclusive),
      subtotalExclusive: subtotalExVat,
      vatAmount: roundMoney(vatAmount),
      total: roundMoney(grossSubtotalInclusive),
    };
  },
};
