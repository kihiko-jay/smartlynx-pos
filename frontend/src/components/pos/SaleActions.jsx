import { useState, useEffect } from "react";

const getButtonStyle = (isMobile) => ({
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

export default function SaleActions({
  cart,
  heldSales,
  setShowHoldList,
  requestSupervisorApproval,
  setLockConfirm,
  lastReceipt,
  handleReprintLastReceipt,
  createHold,
}) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const buttonStyle = getButtonStyle(isMobile);
  const gridColumns = isMobile ? "1fr 1fr" : "1fr";

  return (
    <div className="rms-panel">
      <div className="rms-title" style={{ fontSize: isMobile ? 11 : 12 }}>Sale Actions</div>
      <div style={{ padding: isMobile ? 6 : 10, display: "grid", gridTemplateColumns: gridColumns, gap: isMobile ? 4 : 8 }}>
        <button style={{ ...buttonStyle.utility, opacity: cart.length ? 1 : 0.5 }} onClick={createHold} disabled={!cart.length}>
          Create Hold
        </button>
        <button style={{ ...buttonStyle.utility, opacity: heldSales.length ? 1 : 0.5 }} onClick={() => setShowHoldList(true)} disabled={!heldSales.length}>
          Recall Hold
        </button>
        <button style={buttonStyle.utility} onClick={() => requestSupervisorApproval("return")}>
          Return
        </button>
        <button style={buttonStyle.utility} onClick={() => setLockConfirm(true)}>
          Lock / Change User
        </button>
        <button style={{ ...buttonStyle.utility, opacity: lastReceipt ? 1 : 0.5 }} onClick={handleReprintLastReceipt} disabled={!lastReceipt}>
          Reprint Receipt
        </button>
        <button
          style={{ ...buttonStyle.utility, borderColor: "#7a1f1f", color: "#991b1b" }}
          onClick={() => requestSupervisorApproval("void")}
        >
          Void Sale
        </button>
      </div>
    </div>
  );
}