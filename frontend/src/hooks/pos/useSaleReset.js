export function useSaleReset({
  txnStateRef,
  txnKeyRef,
  cart,
  payment,
  receipts,
  entry,
  entryRef,
}) {
  return () => {
    txnStateRef.current = { isActive: false, endTime: Date.now() };
    txnKeyRef.current = null;
    cart.clearCart();
    payment.resetPaymentState();
    receipts.clearReceipt();
    entry.setEntryInput("");
    entry.setError("");
    setTimeout(() => entryRef.current?.focus(), 50);
  };
}
