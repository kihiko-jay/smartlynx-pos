import { useState, useEffect } from "react";

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
    minHeight: isMobile ? 38 : 54,
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

export default function LockConfirmModal({ lockConfirm, setLockConfirm, openSecureLogin }) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (!lockConfirm) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(3,15,39,.58)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 120,
        padding: isMobile ? 8 : 0,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) setLockConfirm(false);
      }}
    >
      <div className="rms-panel" style={{ width: isMobile ? "100%" : "min(420px, 92vw)", overflow: "hidden" }}>
        <div className="rms-title" style={{ fontSize: isMobile ? 12 : 14 }}>Lock Screen / Change User</div>
        <div style={{ padding: isMobile ? 12 : 18 }}>
          <div style={{ marginBottom: isMobile ? 12 : 16, color: "#334155", fontSize: isMobile ? 12 : 14 }}>
            Lock this terminal and require a fresh backend-authenticated login before use continues.
          </div>

          <div style={{ display: "grid", gap: isMobile ? 8 : 10 }}>
            <button
              style={{
                ...getActionButtonStyle(isMobile),
                minHeight: isMobile ? 38 : 46,
              }}
              onClick={() => {
                setLockConfirm(false);
                openSecureLogin();
              }}
            >
              Unlock / Change User
            </button>

            <button
              style={getUtilityButtonStyle(isMobile)}
              onClick={() => setLockConfirm(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}