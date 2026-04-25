import { useEffect, useMemo, useRef } from "react";
import { parseCashInputToCents, parseMoneyToCents, subCents, fmtKESCents } from "../../utils/money";
import { PAYMENT_METHODS } from "../../modules/pos/paymentMethods";

function buttonStyle(selected) {
  return {
    border: selected ? "2px solid #155eef" : "1px solid #94a3b8",
    borderRadius: 8,
    background: selected ? "#dbeafe" : "#fff",
    color: selected ? "#0b3ea8" : "#1f2937",
    minHeight: 44,
    fontWeight: 700,
    cursor: "pointer",
    outline: "none",
  };
}

export default function PaymentModal({
  open,
  total,
  paymentMode,
  setPaymentMode,
  cashInput,
  setCashInput,
  mpesaPhone,
  setMpesaPhone,
  loading,
  canConfirm,
  error,
  onClose,
  onConfirm,
  restoreFocusRef,
}) {
  const modalRef = useRef(null);
  const methodRefs = useRef([]);
  const amountInputRef = useRef(null);
  const phoneInputRef = useRef(null);
  const confirmBtnRef = useRef(null);

  const cashCents = parseCashInputToCents(cashInput);
  const totalCents = parseMoneyToCents(total);
  const changeCents = subCents(cashCents, totalCents);
  const amountRequired = paymentMode === "cash";
  const phoneRequired = paymentMode === "mpesa";

  useMemo(
    () => PAYMENT_METHODS.findIndex((method) => method.id === paymentMode),
    [paymentMode]
  );

  useEffect(() => {
    if (!open) return undefined;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    let initialFocus = methodRefs.current[0];
    if (paymentMode === "cash") initialFocus = amountInputRef.current;
    if (paymentMode === "mpesa") initialFocus = phoneInputRef.current;
    if (!paymentMode) initialFocus = methodRefs.current[0];

    setTimeout(() => initialFocus?.focus(), 0);

    return () => {
      document.body.style.overflow = prevOverflow;
      restoreFocusRef?.current?.focus?.();
    };
  }, [open, paymentMode, restoreFocusRef]);

  useEffect(() => {
    if (!open) return undefined;

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose?.();
        return;
      }

      if (event.key === "Tab" && modalRef.current) {
        const focusables = modalRef.current.querySelectorAll(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];

        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Payment"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(3,15,39,.62)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 250,
        padding: 16,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !loading) onClose?.();
      }}
    >
      <div className="rms-panel" ref={modalRef} style={{ width: "min(620px, 94vw)" }}>
        <div className="rms-title">Payment</div>

        <div style={{ padding: 12, display: "grid", gap: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 800 }}>
            <span>Order Total</span>
            <span>{fmtKESCents(parseMoneyToCents(total))}</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8 }}>
            {PAYMENT_METHODS.map((method, idx) => (
              <button
                key={method.id}
                ref={(node) => {
                  methodRefs.current[idx] = node;
                }}
                type="button"
                style={buttonStyle(paymentMode === method.id)}
                onClick={() => setPaymentMode(method.id)}
                onKeyDown={(event) => {
                  if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                    event.preventDefault();
                    const next = (idx + 1) % PAYMENT_METHODS.length;
                    methodRefs.current[next]?.focus();
                  }
                  if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                    event.preventDefault();
                    const prev = (idx - 1 + PAYMENT_METHODS.length) % PAYMENT_METHODS.length;
                    methodRefs.current[prev]?.focus();
                  }
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setPaymentMode(method.id);
                  }
                }}
              >
                {method.label}
              </button>
            ))}
          </div>

          {amountRequired && (
            <>
              <label style={{ fontSize: 12, fontWeight: 700 }} htmlFor="payment-cash-input">
                Amount Received
              </label>
              <input
                id="payment-cash-input"
                ref={amountInputRef}
                className="rms-input"
                value={cashInput}
                type="number"
                min="0"
                step="0.01"
                onChange={(e) => setCashInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && canConfirm && !loading) onConfirm?.();
                }}
              />
              <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700 }}>
                <span>Change</span>
                <span style={{ color: changeCents >= 0 ? "#15803d" : "#b42318" }}>
                  {fmtKESCents(changeCents)}
                </span>
              </div>
            </>
          )}


          {paymentMode === "store_credit" && (
            <div
              style={{
                border: "1px dashed #94a3b8",
                borderRadius: 8,
                padding: 10,
                color: "#475569",
                fontSize: 12,
              }}
            >
              Requires a selected customer with enough wallet balance to cover the full order.
            </div>
          )}

          {phoneRequired && (
            <>
              <label style={{ fontSize: 12, fontWeight: 700 }} htmlFor="payment-mpesa-phone">
                M-PESA Phone Number
              </label>
              <input
                id="payment-mpesa-phone"
                ref={phoneInputRef}
                className="rms-input"
                value={mpesaPhone}
                type="text"
                placeholder="07XXXXXXXX"
                onChange={(e) => setMpesaPhone(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && canConfirm && !loading) onConfirm?.();
                }}
              />
              <div
                style={{
                  border: "1px dashed #94a3b8",
                  borderRadius: 8,
                  padding: 10,
                  color: "#475569",
                  fontSize: 12,
                }}
              >
                Confirming will create the pending sale first, then send the STK push.
              </div>
            </>
          )}

          {!amountRequired && !phoneRequired && (
            <div style={{ border: "1px dashed #94a3b8", borderRadius: 8, padding: 10, color: "#475569" }}>
              No manual entry required for this payment method.
            </div>
          )}

          {!!error && <div style={{ color: "#b42318", fontWeight: 700 }}>{error}</div>}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              style={{ minHeight: 42, fontWeight: 700 }}
            >
              Cancel (Esc)
            </button>

            <button
              ref={confirmBtnRef}
              type="button"
              onClick={onConfirm}
              disabled={!canConfirm || loading}
              style={{
                minHeight: 42,
                fontWeight: 800,
                background: "#155eef",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                opacity: !canConfirm || loading ? 0.6 : 1,
              }}
            >
              {loading
                ? "Processing..."
                : paymentMode === "mpesa"
                ? "Send STK Push"
                : "Confirm Payment"}
            </button>
          </div>

          <div style={{ color: "#64748b", fontSize: 12 }}>
            Shortcut: Press F9 on checkout to open this modal.
          </div>
        </div>
      </div>
    </div>
  );
}