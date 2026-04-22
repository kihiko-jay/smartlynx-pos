import { useState, useEffect } from "react";
import { fmtKES } from "../../api/client";

const getButtonStyle = (isMobile) => ({
  action: {
    background: "linear-gradient(180deg, #1b6cff 0%, #0d4fd6 100%)",
    border: "1px solid #2f65d9",
    borderRadius: 6,
    color: "#fff",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: isMobile ? 11 : 12,
    fontWeight: 700,
    letterSpacing: "0.04em",
    minHeight: isMobile ? 40 : 54,
    padding: isMobile ? "8px 10px" : "10px 12px",
    textTransform: "uppercase",
  },
  utility: {
    background: "#0f1724",
    border: "1px solid #22304a",
    borderRadius: 6,
    color: "#d6e2ff",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: isMobile ? 11 : 12,
    fontWeight: 700,
    minHeight: isMobile ? 38 : 48,
    padding: isMobile ? "6px 8px" : "8px 10px",
  },
});

export default function SaleCompletion({
  error,
  receipt,
  loading,
  canComplete,
  handleCompleteSale,
  handlePrintReceipt,
  handleWhatsAppReceipt,
  clearCart,
}) {
  const [countdown, setCountdown] = useState(0);
  const [showCountdown, setShowCountdown] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Timer for auto-reset countdown
  useEffect(() => {
    if (receipt) {
      setShowCountdown(true);
      setCountdown(5);
      const interval = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(interval);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(interval);
    } else {
      setShowCountdown(false);
      setCountdown(0);
    }
  }, [receipt]);

  const buttonStyles = getButtonStyle(isMobile);
  const buttonGridLayout = isMobile ? "1fr" : "1fr 1fr";

  return (
    <div className="rms-panel" style={{ padding: isMobile ? 6 : 10 }}>
      {error && <div style={{ color: "#b42318", fontWeight: 700, marginBottom: 8, fontSize: isMobile ? 11 : 12 }}>{error}</div>}
      {!receipt ? (
        <button
          onClick={handleCompleteSale}
          disabled={!canComplete}
          style={{
            ...buttonStyles.action,
            width: "100%",
            minHeight: isMobile ? 48 : 64,
            fontSize: isMobile ? 14 : 18,
            opacity: canComplete ? 1 : 0.45,
            cursor: canComplete ? "pointer" : "not-allowed",
          }}
        >
          {loading ? "Processing..." : "Complete Sale"}
        </button>
      ) : (
        <div>
          <div style={{ color: "#15803d", fontSize: isMobile ? 14 : 18, fontWeight: 800, marginBottom: 6 }}>Sale Complete</div>
          <div style={{ marginBottom: 4, fontWeight: 700, fontSize: isMobile ? 12 : 14 }}>{receipt.txn_number}</div>
          <div style={{ marginBottom: 10, fontSize: isMobile ? 12 : 14 }}>Total: <strong>{fmtKES(receipt.total)}</strong></div>
          
          {showCountdown && countdown > 0 && (
            <div style={{
              marginBottom: 10,
              padding: 8,
              background: "rgba(15, 143, 54, 0.1)",
              border: "1px solid #0f8f36",
              borderRadius: 6,
              textAlign: "center",
              color: "#0f8f36",
              fontWeight: 700,
              fontSize: isMobile ? 11 : 13,
            }}>
              Auto-starting new transaction in {countdown}s...
            </div>
          )}
          
          <div style={{ display: "grid", gridTemplateColumns: buttonGridLayout, gap: isMobile ? 4 : 8 }}>
            <button style={buttonStyles.utility} onClick={handlePrintReceipt}>Print</button>
            <button style={buttonStyles.utility} onClick={handleWhatsAppReceipt}>WhatsApp</button>
            <button 
              style={{ ...buttonStyles.action, gridColumn: isMobile ? "1 / -1" : "1 / -1" }} 
              onClick={() => {
                setShowCountdown(false);
                clearCart();
              }}
            >
              New Transaction
            </button>
          </div>
        </div>
      )}
    </div>
  );
}