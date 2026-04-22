import { transactionsAPI, etimsAPI, mpesaAPI } from "../api/client";
import { pricingService } from "./pricingService";

function generateTxnNumber() {
  const ts = Date.now().toString(36).toUpperCase();
  const rnd = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `TXN-${ts}-${rnd}`;
}

export const transactionService = {
  generateTxnNumber,

  // Create transaction (online or offline via queue)
  createTransaction: async (payload, idempotencyKey, { enqueue, isOnline }) => {
    if (!isOnline) {
      // Queue offline transaction
      await enqueue({ ...payload, offline_txn_number: idempotencyKey });
      return null;
    }

    try {
      const txn = await transactionsAPI.create(payload, {
        headers: { "Idempotency-Key": idempotencyKey },
      });

      // Submit to eTIMS asynchronously
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

  // Build transaction payload from cart and payment data
  buildTransactionPayload(cart, sessionTerminalId, paymentMode, cashGiven, mpesaPhone, options = {}) {
    const { customerId = null, cashSessionId = null, discountAmount = "0.00" } = options;

    return {
      terminal_id: sessionTerminalId || "T01",
      payment_method: paymentMode,
      discount_amount: Number(discountAmount || 0).toFixed(2),
      cash_tendered: paymentMode === "cash" ? Number(cashGiven || 0).toFixed(2) : null,
      mpesa_phone: paymentMode === "mpesa" ? mpesaPhone : null,
      customer_id: ["credit", "store_credit"].includes(paymentMode) ? customerId : null,
      cash_session_id: paymentMode === "cash" ? cashSessionId : null,
      items: cart.map((i) => ({
        product_id: i.id,
        qty: i.qty,
        unit_price: Number(pricingService.getPriceExclusive(i)).toFixed(2),
        discount: Number(i.discount || 0).toFixed(2),
      })),
    };
  },

  // Build offline receipt (for when no connectivity)
  buildOfflineReceipt: (txnNumber, cart, payment, totals) => {
    return {
      txn_number: txnNumber,
      total: totals.total.toFixed(2),
      subtotal: totals.subtotalExclusive.toFixed(2),
      gross_subtotal: totals.subtotalInclusive.toFixed(2),
      discount_amount: "0.00",
      vat_amount: totals.vatAmount.toFixed(2),
      payment_method: payment.mode,
      items: cart.map((i) => ({
        ...i,
        line_total: i.unit_price_inclusive * i.qty,
      })),
      etims_synced: false,
      sync_status: "local",
    };
  },

  // Push M-Pesa STK prompt
  pushMpesaPrompt: async (phone, amount, txnNumber) => {
    try {
      await mpesaAPI.stkPush(phone, amount, txnNumber);
    } catch (e) {
      throw new Error(e.message || "M-Pesa push failed");
    }
  },
};
