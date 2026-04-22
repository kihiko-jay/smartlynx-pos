import { mpesaAPI } from "../../api/client";
import { pricingService } from "../../services/pricingService";

export const paymentFlow = {
  // Handle M-Pesa push
  handleMpesaPush: async (phone, total, txnNumber) => {
    try {
      await mpesaAPI.stkPush(phone, total, txnNumber);
    } catch (e) {
      throw new Error(e.message || "M-Pesa payment initiation failed");
    }
  },

  // Validate cash payment
  validateCashPayment: (cashTendered, total) => {
    const roundedCash = Math.round((Number(cashTendered) + Number.EPSILON) * 100) / 100;
    const roundedTotal = Math.round((Number(total) + Number.EPSILON) * 100) / 100;
    
    if (roundedCash < roundedTotal) {
      const { fmtKES } = require("../../api/client");
      return {
        valid: false,
        error: `Cash tendered (${fmtKES(roundedCash)}) is less than total (${fmtKES(roundedTotal)}). Please enter a sufficient amount.`,
      };
    }
    return { valid: true };
  },

  // Check if sale can be completed
  canCompleteSale: (cart, paymentMode, cashInput, mpesaStatus, loading, total, currentCashSession) => {

    if (cart.length === 0 || loading) return false;
    if (paymentMode === "cash" && !currentCashSession) return false;
    if (paymentMode === "cash") {
      const cashTendered = Math.round(parseFloat(cashInput)) || 0;
      const roundedTotal = Math.round(total);
      return cashTendered >= roundedTotal;
    }

    if (paymentMode === "card" || paymentMode === "credit" || paymentMode === "store_credit") return true;

    if (paymentMode === "mpesa") {
      return mpesaStatus === null || mpesaStatus === "confirmed";
    }

    return false;
  },

  // Calculate change for cash payment
  calculateChange: (cashTendered, total) => {
    const roundedCash = Math.round((Number(cashTendered) + Number.EPSILON) * 100) / 100;
    const roundedTotal = Math.round((Number(total) + Number.EPSILON) * 100) / 100;
    return Math.max(0, roundedCash - roundedTotal);
  },

  // Reset payment state for new transaction
  resetPaymentState: () => ({
    paymentMode: null,
    cashInput: "",
    mpesaPhone: "07",
    mpesaStatus: null,
    mpesaFailMsg: "",
  }),
};
