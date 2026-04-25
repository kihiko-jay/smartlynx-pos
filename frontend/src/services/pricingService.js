import {
  parseMoneyToCents,
  mulCentsByQty,
  addCents,
  subCents,
  splitInclusiveGrossKenya16,
  vatOnExclusiveNetKenya16,
  centsToDisplayNumber,
} from "../utils/money";

const VAT_RATE = 0.16;
/** Shelf prices are VAT-inclusive (Kenya POS); must match transaction payload `prices_include_vat`. */
export const PRICES_INCLUDE_VAT = true;

export const pricingService = {
  getItemVatRate(item) {
    if (item.vat_exempt) return 0;
    if (["VAT_EXEMPT", "ZERO_RATED", "ZERO"].includes(item.tax_code)) return 0;
    return VAT_RATE;
  },

  getPriceInclusive(item) {
    return centsToDisplayNumber(parseMoneyToCents(item.selling_price ?? item.price ?? 0));
  },

  getPriceExclusive(item) {
    const inclusiveCents = parseMoneyToCents(item.selling_price ?? item.price ?? 0);
    const rate = this.getItemVatRate(item);
    if (PRICES_INCLUDE_VAT && rate > 0) {
      const { netCents } = splitInclusiveGrossKenya16(inclusiveCents);
      return centsToDisplayNumber(netCents);
    }
    return centsToDisplayNumber(inclusiveCents);
  },

  getDisplayPrice(item) {
    return centsToDisplayNumber(parseMoneyToCents(item.selling_price ?? item.price ?? 0));
  },

  /**
   * Cart totals in minor units then stable display numbers (subtotal ex-VAT, VAT, total payable).
   */
  calculateTotals(cart) {
    let grossInclusiveCents = 0;
    let vatAmountCents = 0;
    let subtotalExCents = 0;

    for (const i of cart) {
      const unitCents = parseMoneyToCents(i.selling_price ?? i.price ?? 0);
      const discCents = parseMoneyToCents(i.discount || 0);
      const lineGrossCents = subCents(mulCentsByQty(unitCents, i.qty), discCents);
      grossInclusiveCents = addCents(grossInclusiveCents, lineGrossCents);

      const rate = this.getItemVatRate(i);
      if (PRICES_INCLUDE_VAT) {
        if (rate > 0) {
          const { netCents, vatCents } = splitInclusiveGrossKenya16(lineGrossCents);
          subtotalExCents = addCents(subtotalExCents, netCents);
          vatAmountCents = addCents(vatAmountCents, vatCents);
        } else {
          subtotalExCents = addCents(subtotalExCents, lineGrossCents);
        }
      } else {
        subtotalExCents = addCents(subtotalExCents, lineGrossCents);
        if (rate > 0) {
          vatAmountCents = addCents(vatAmountCents, vatOnExclusiveNetKenya16(lineGrossCents));
        }
      }
    }

    const totalCents = PRICES_INCLUDE_VAT ? grossInclusiveCents : addCents(subtotalExCents, vatAmountCents);

    return {
      subtotalInclusive: centsToDisplayNumber(grossInclusiveCents),
      subtotalExclusive: centsToDisplayNumber(subtotalExCents),
      vatAmount: centsToDisplayNumber(vatAmountCents),
      total: centsToDisplayNumber(totalCents),
      totalCents,
      subtotalExclusiveCents: subtotalExCents,
      vatAmountCents,
      subtotalInclusiveCents: grossInclusiveCents,
    };
  },
};
