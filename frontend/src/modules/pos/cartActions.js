import { pricingService } from "../../services/pricingService";

export const cartActions = {
  // Create hold from current cart
  createHold: (cart, paymentMode, cashInput, mpesaPhone, subtotalExVat, vatAmount, total) => {
    if (!cart.length) {
      throw new Error("There is no active sale to hold.");
    }

    return {
      id: `HOLD-${Date.now()}`,
      created_at: new Date().toISOString(),
      cart,
      paymentMode,
      cashInput,
      mpesaPhone,
      subtotal: subtotalExVat,
      vat_amount: vatAmount,
      total,
      lines: cart.length,
      units: cart.reduce((s, i) => s + i.qty, 0),
    };
  },

  // Add created hold to list and clear cart
  saveHold: (hold, heldSales, saveHeldSales, clearCartFn) => {
    const next = [hold, ...heldSales].slice(0, 20);
    saveHeldSales(next);
    clearCartFn?.();
  },

  // Restore hold to active cart
  recallHold: (holdId, heldSales, saveHeldSales, setCart, setSelectedCartId, setPaymentMode, setCashInput, setMpesaPhone) => {
    const hold = heldSales.find((h) => h.id === holdId);
    if (!hold) return false;

    setCart(hold.cart || []);
    setSelectedCartId(hold.cart?.[0]?.id || null);
    setPaymentMode(hold.paymentMode || null);
    setCashInput(hold.cashInput || "");
    setMpesaPhone(hold.mpesaPhone || "07");

    const remaining = heldSales.filter((h) => h.id !== holdId);
    saveHeldSales(remaining);

    return true;
  },
};
