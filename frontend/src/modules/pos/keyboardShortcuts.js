export function setupKeyboardShortcuts({
  onF2,
  onF9,
  onEscape,
  cart,
  receipt,
  total,
  loading,
  modalOpen = false,
}) {
  const handler = (e) => {
    // F2: Open product search
    if (e.key === "F2") {
      e.preventDefault();
      onF2?.("");
    }

    // F9: Open payment modal from POS checkout
    if (e.key === "F9") {
      e.preventDefault();
      const allowed = shouldOpenPaymentModal({ cart, total, loading, receipt });
      onF9?.({ modalOpen, allowed });
    }

    // Escape: Clear receipt (new transaction)
    if (e.key === "Escape" && receipt) {
      e.preventDefault();
      onEscape?.();
    }
  };

  window.addEventListener("keydown", handler);

  return () => window.removeEventListener("keydown", handler);
}

export function shouldOpenPaymentModal({ cart, total, loading, receipt }) {
  if (loading || receipt) return false;
  if (!Array.isArray(cart) || cart.length === 0) return false;
  const resolvedTotal =
    typeof total === "number"
      ? total
      : cart.reduce((sum, i) => sum + (i.selling_price ?? i.price ?? 0) * i.qty, 0);
  return resolvedTotal > 0;
}
