import { useState, useEffect } from "react";
import { fmtKES } from "../../api/client";

function getButtonStyle(isMobile) {
  return {
    background: "#0f1724",
    border: "1px solid #22304a",
    borderRadius: 6,
    color: "#d6e2ff",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: isMobile ? 11 : 12,
    fontWeight: 700,
    minHeight: isMobile ? 34 : 38,
    padding: isMobile ? "4px 8px" : "0 12px",
  };
}

export default function HeldSalesModal({ showHoldList, setShowHoldList, heldSales, recallHold }) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (!showHoldList) return null;

  const gridLayout = isMobile ? "1fr auto" : "1.2fr 1fr 1fr auto";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(3,15,39,.58)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: isMobile ? 40 : 70,
        zIndex: 110,
        padding: isMobile ? 8 : 0,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) setShowHoldList(false);
      }}
    >
      <div className="rms-panel" style={{ width: isMobile ? "100%" : "min(720px, 92vw)", overflow: "hidden" }}>
        <div className="rms-title" style={{ fontSize: isMobile ? 12 : 14 }}>Held Sales</div>
        <div style={{ maxHeight: isMobile ? 300 : 420, overflowY: "auto", background: "#fff" }}>
          {!heldSales.length ? (
            <div style={{ padding: isMobile ? 16 : 24, textAlign: "center", color: "#64748b", fontSize: isMobile ? 12 : 14 }}>
              No held sales available.
            </div>
          ) : (
            heldSales.map((hold, idx) => (
              <div
                key={hold.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: gridLayout,
                  gap: isMobile ? 4 : 8,
                  padding: isMobile ? "8px 10px" : "12px 14px",
                  borderTop: idx ? "1px solid #e2e8f0" : "none",
                  alignItems: "center",
                }}
              >
                <div>
                  <div style={{ fontWeight: 700, color: "#155eef", fontSize: isMobile ? 12 : 13 }}>{hold.id}</div>
                  <div style={{ fontSize: isMobile ? 10 : 12, color: "#64748b", marginTop: 2 }}>
                    {new Date(hold.created_at).toLocaleString("en-KE", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </div>
                </div>
                {!isMobile && <div style={{ fontWeight: 700, fontSize: 12 }}>{fmtKES(hold.total)}</div>}
                {!isMobile && <div style={{ color: "#64748b", fontSize: 12 }}>
                  {hold.lines || 0} lines · {hold.units || 0} units
                </div>}
                {isMobile && <div style={{ color: "#64748b", fontSize: 11, textAlign: "right" }}>
                  {fmtKES(hold.total)}<br />{hold.lines || 0}L {hold.units || 0}U
                </div>}
                <button style={getButtonStyle(isMobile)} onClick={() => recallHold(hold.id)}>
                  Recall
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}