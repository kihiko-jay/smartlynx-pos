import { useState, useEffect } from "react";

export default function SessionOverview({
  session,
  currentCashSession,
  cart,
  isOnline,
}) {
  const [isMobile, setIsMobile] = useState(
    typeof window !== "undefined" && window.innerWidth < 768
  );

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const totalQty = cart.reduce((s, i) => s + i.qty, 0);
  const gridColumns = isMobile ? "1fr 1fr" : "1.3fr 1fr 1fr 1fr";
  const shiftStatus = currentCashSession
    ? "SHIFT OPEN"
    : "NO OPEN SHIFT";
  const shiftDisplay = currentCashSession
    ? `${currentCashSession.session_number || "Session"}`
    : "No open session";

  return (
    <div className="rms-panel">
      <div className="rms-title" style={{ fontSize: isMobile ? 11 : 12 }}>
        Customer / Session Overview
      </div>
      <div style={{ display: "grid", gridTemplateColumns: gridColumns, gap: 0 }}>
        {[
          ["Store", session?.store_name || "Demo Duka Store"],
          ["User", session?.name || "Cashier"],
          ["Total Qty", totalQty],
          ["Status", isOnline ? "ONLINE" : "OFFLINE"],
          ["Shift", shiftStatus],
          ["Cash Session", shiftDisplay],
        ].map(([label, value]) => (
          <div
            key={label}
            style={{
              padding: isMobile ? "8px 10px" : "10px 12px",
              borderRight:
                isMobile && label !== "Store" && label !== "User"
                  ? "none"
                  : "1px solid #cbd5e1",
              borderBottom: isMobile ? "1px solid #cbd5e1" : "none",
              background:
                (label === "Shift" && !currentCashSession) ||
                (label === "Cash Session" && !currentCashSession)
                  ? "#fef3c7"
                  : "transparent",
            }}
          >
            <div
              style={{
                color: "#155eef",
                fontSize: isMobile ? 10 : 11,
                fontWeight: 700,
                marginBottom: 3,
                textTransform: "uppercase",
              }}
            >
              {label}
            </div>
            <div
              style={{
                fontSize: isMobile ? 13 : 15,
                fontWeight: 700,
                color:
                  (label === "Shift" || label === "Cash Session") &&
                  !currentCashSession
                    ? "#d97706"
                    : "#111827",
              }}
            >
              {value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}