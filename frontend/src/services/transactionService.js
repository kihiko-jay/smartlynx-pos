import { transactionsAPI, etimsAPI, mpesaAPI } from "../api/client";
import { PRICES_INCLUDE_VAT } from "./pricingService";
import { centsToApiString, parseMoneyToCents, parseCashInputToCents, mulCentsByQty, subCents } from "../utils/money";

function generateTxnNumber() {
  const ts = Date.now().toString(36).toUpperCase();
  const rnd = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `TXN-${ts}-${rnd}`;
}

export const transactionService = {
  generateTxnNumber,

  createTransaction: async (payload, idempotencyKey, { enqueue, isOnline }) => {
    if (!isOnline) {
      await enqueue({ ...payload, offline_txn_number: idempotencyKey });
      return null;
    }

    try {
      const txn = await transactionsAPI.create(payload, {
        headers: { "Idempotency-Key": idempotencyKey },
      });

      etimsAPI.submit(txn.id).catch((err) =>
        console.warn("eTIMS submit failed (will retry):", err.message)
      );

      return txn;
    } catch (e) {
      throw new Error(
        e.message?.includes("Too many")
          ? "Too many requests. Please wait a moment and try again."
          : e.message || "Transaction failed"
      );
    }
  },

  buildTransactionPayload(cart, sessionTerminalId, paymentMode, cashGiven, mpesaPhone, options = {}) {
    const { customerId = null, cashSessionId = null, discountAmount = "0.00" } = options;

    const discountCents = parseMoneyToCents(discountAmount);
    const cashCents =
      paymentMode === "cash" ? parseCashInputToCents(cashGiven == null ? "" : String(cashGiven)) : 0;

    return {
      terminal_id: sessionTerminalId || "T01",
      payment_method: paymentMode,
      discount_amount: centsToApiString(discountCents),
      cash_tendered: paymentMode === "cash" ? centsToApiString(cashCents) : null,
      mpesa_phone: paymentMode === "mpesa" ? mpesaPhone : null,
      customer_id: ["credit", "store_credit"].includes(paymentMode) ? customerId : null,
      cash_session_id: paymentMode === "cash" ? cashSessionId : null,
      prices_include_vat: PRICES_INCLUDE_VAT,
      items: cart.map((i) => {
        const unitCents = parseMoneyToCents(i.selling_price ?? i.price ?? 0);
        const discCents = parseMoneyToCents(i.discount || 0);
        return {
          product_id: i.id,
          qty: i.qty,
          unit_price: centsToApiString(unitCents),
          discount: centsToApiString(discCents),
        };
      }),
    };
  },

  buildOfflineReceipt: (txnNumber, cart, payment, totals) => {
    return {
      txn_number: txnNumber,
      total: centsToApiString(parseMoneyToCents(totals.total)),
      subtotal: centsToApiString(parseMoneyToCents(totals.subtotalExclusive)),
      gross_subtotal: centsToApiString(parseMoneyToCents(totals.subtotalInclusive)),
      discount_amount: "0.00",
      vat_amount: centsToApiString(parseMoneyToCents(totals.vatAmount)),
      payment_method: payment.mode,
      items: cart.map((i) => {
        const unitCents = parseMoneyToCents(i.selling_price ?? i.price ?? 0);
        const lineGross = subCents(mulCentsByQty(unitCents, i.qty), parseMoneyToCents(i.discount || 0));
        return {
          ...i,
          line_total: centsToApiString(lineGross),
        };
      }),
      etims_synced: false,
      sync_status: "local",
    };
  },

  pushMpesaPrompt: async (phone, amount, txnNumber) => {
    try {
      const amountStr = centsToApiString(parseMoneyToCents(amount));
      await mpesaAPI.stkPush(phone, amountStr, txnNumber);
    } catch (e) {
      throw new Error(e.message || "M-Pesa push failed");
    }
  },
};
