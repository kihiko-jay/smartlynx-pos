import { useState, useEffect } from "react";

function getActionDisplayName(action) {
  const displayNames = {
    "delete-item": "Delete Item",
    "void": "Void Sale",
    "return": "Return",
  };
  return displayNames[action] || action?.toUpperCase();
}

function getActionButtonStyle(isMobile) {
  return {
    background: "linear-gradient(180deg, #1b6cff 0%, #0d4fd6 100%)",
    border: "1px solid #2f65d9",
    borderRadius: 8,
    color: "#fff",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: isMobile ? 11 : 12,
    fontWeight: 700,
    letterSpacing: "0.04em",
    minHeight: isMobile ? 42 : 54,
    padding: isMobile ? "6px 8px" : "10px 12px",
    textTransform: "uppercase",
  };
}

function getUtilityButtonStyle(isMobile) {
  return {
    background: "#0f1724",
    border: "1px solid #22304a",
    borderRadius: 8,
    color: "#d6e2ff",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: isMobile ? 11 : 12,
    fontWeight: 700,
    minHeight: isMobile ? 38 : 48,
  };
}

export default function SupervisorModal({
  showSupervisorModal,
  setShowSupervisorModal,
  pendingSupervisorAction,
  supervisorEmail,
  setSupervisorEmail,
  supervisorPin,
  setSupervisorPin,
  confirmSupervisorAction,
  supervisorLoading,
}) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (!showSupervisorModal) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(3,15,39,.58)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 126,
        padding: isMobile ? 8 : 0,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) setShowSupervisorModal(false);
      }}
    >
      <div className="rms-panel" style={{ width: isMobile ? "100%" : "min(420px, 92vw)", overflow: "hidden" }}>
        <div className="rms-title" style={{ fontSize: isMobile ? 12 : 14 }}>Supervisor Approval Required</div>
        <div style={{ padding: isMobile ? 12 : 18, display: "grid", gap: isMobile ? 10 : 12 }}>
          <div style={{ fontSize: isMobile ? 12 : 14, color: "#334155" }}>
            Action: <strong>{getActionDisplayName(pendingSupervisorAction)}</strong>
          </div>

          <input
            className="rms-input"
            type="email"
            placeholder="Supervisor email"
            value={supervisorEmail}
            onChange={(e) => setSupervisorEmail(e.target.value)}
            style={{ fontSize: isMobile ? 13 : 14 }}
          />

          <input
            className="rms-input"
            type="password"
            placeholder="Supervisor password"
            value={supervisorPin}
            onChange={(e) => setSupervisorPin(e.target.value)}
            style={{ fontSize: isMobile ? 13 : 14 }}
          />

          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: isMobile ? 8 : 10 }}>
            <button
              style={getActionButtonStyle(isMobile)}
              onClick={confirmSupervisorAction}
              disabled={supervisorLoading}
            >
              {supervisorLoading ? "Approving..." : "Approve"}
            </button>
            <button style={getUtilityButtonStyle(isMobile)} onClick={() => setShowSupervisorModal(false)}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}