import { fmtKES } from "../../api/client";

export default function PaymentSection({
  paymentMode,
  total,
  receipt,
  mpesaStatus,
  mpesaFailMsg,
}) {
  return (
    <div className="rms-panel">
      <div className="rms-title">Payment Status</div>

      <div style={{ padding: 10, display: "grid", gap: 10 }}>
        <div
          style={{
            border: "1px solid #cbd5e1",
            borderRadius: 6,
            padding: 10,
            background: "#fff",
          }}
        >
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, fontWeight: 700 }}>
            CURRENT TOTAL
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: "#155eef" }}>
            {fmtKES(total)}
          </div>
        </div>

        <div
          style={{
            border: "1px solid #cbd5e1",
            borderRadius: 6,
            padding: 10,
            background: "#fff",
          }}
        >
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, fontWeight: 700 }}>
            SELECTED METHOD
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#111827" }}>
            {paymentMode ? paymentMode.toUpperCase() : "Not selected"}
          </div>
        </div>

        {paymentMode === "mpesa" && (
          <div
            style={{
              border: "1px dashed #94a3b8",
              borderRadius: 6,
              padding: 10,
              background: "#f8fafc",
              color: "#475569",
              fontSize: 12,
              lineHeight: 1.5,
            }}
          >
            Press <strong>F9</strong> or use the payment modal to enter the M-PESA phone number
            and confirm payment. The system will create a pending transaction first, then send
            the STK push.
          </div>
        )}

        {mpesaStatus === "waiting" && (
          <div
            style={{
              border: "1px solid #93c5fd",
              background: "#eff6ff",
              color: "#1d4ed8",
              borderRadius: 6,
              padding: 10,
              fontWeight: 700,
              fontSize: 12,
            }}
          >
            Waiting for M-PESA confirmation...
          </div>
        )}

        {mpesaStatus === "confirmed" && (
          <div
            style={{
              border: "1px solid #86efac",
              background: "#f0fdf4",
              color: "#15803d",
              borderRadius: 6,
              padding: 10,
              fontWeight: 700,
              fontSize: 12,
            }}
          >
            M-PESA payment confirmed.
          </div>
        )}

        {mpesaStatus === "failed" && (
          <div
            style={{
              border: "1px solid #fca5a5",
              background: "#fef2f2",
              color: "#b42318",
              borderRadius: 6,
              padding: 10,
              fontWeight: 700,
              fontSize: 12,
            }}
          >
            {mpesaFailMsg || "M-PESA payment failed"}
          </div>
        )}

        {receipt && (
          <div
            style={{
              border: "1px solid #bbf7d0",
              background: "#f0fdf4",
              color: "#15803d",
              borderRadius: 6,
              padding: 10,
              fontWeight: 700,
              fontSize: 12,
            }}
          >
            Sale recorded: {receipt.txn_number}
          </div>
        )}
      </div>
    </div>
  );
}