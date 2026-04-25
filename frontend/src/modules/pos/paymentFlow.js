import { mpesaAPI } from "../../api/client";
import {
  parseCashInputToCents,
  parseMoneyToCents,
  subCents,
  fmtKESCents,
  centsToApiString,
} from "../../utils/money";

export const paymentFlow = {
  handleMpesaPush: async (phone, total, txnNumber) => {
    try {
      await mpesaAPI.stkPush(phone, centsToApiString(parseMoneyToCents(total)), txnNumber);
    } catch (e) {
      throw new Error(e.message || "M-Pesa payment initiation failed");
    }
  },

  validateCashPayment: (cashTendered, total) => {
    const cashCents = parseCashInputToCents(
      cashTendered == null ? "" : String(cashTendered)
    );
    const totalCents = parseMoneyToCents(total);

    if (cashCents < totalCents) {
      return {
        valid: false,
        error: `Cash tendered (${fmtKESCents(cashCents)}) is less than total (${fmtKESCents(totalCents)}). Please enter a sufficient amount.`,
      };
    }
    return { valid: true };
  },

  canCompleteSale: (cart, paymentMode, cashInput, mpesaStatus, loading, total, currentCashSession) => {
    if (cart.length === 0 || loading) return false;
    if (paymentMode === "cash" && !currentCashSession) return false;
    if (paymentMode === "cash") {
      const cashCents = parseCashInputToCents(cashInput || "");
      const totalCents = parseMoneyToCents(total);
      return cashCents >= totalCents;
    }

    if (paymentMode === "card" || paymentMode === "credit" || paymentMode === "store_credit") return true;

    if (paymentMode === "mpesa") {
      return mpesaStatus === null || mpesaStatus === "confirmed";
    }

    return false;
  },

  calculateChange: (cashTendered, total) => {
    const cashCents = parseCashInputToCents(
      cashTendered == null ? "" : String(cashTendered)
    );
    const totalCents = parseMoneyToCents(total);
    const diff = subCents(cashCents, totalCents);
    return diff > 0 ? diff / 100 : 0;
  },

  resetPaymentState: () => ({
    paymentMode: null,
    cashInput: "",
    mpesaPhone: "07",
    mpesaStatus: null,
    mpesaFailMsg: "",
  }),
};
