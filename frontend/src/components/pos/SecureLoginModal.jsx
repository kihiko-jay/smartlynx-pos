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

export default function SecureLoginModal({
  showSecureLogin,
  closeSecureLogin,
  secureEmail,
  setSecureEmail,
  securePassword,
  setSecurePassword,
  secureError,
  handleSecureLogin,
  secureLoading,
  clearSession,
  onNavigate,
}) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (!showSecureLogin) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(3,15,39,.72)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 130,
        padding: isMobile ? 8 : 0,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) closeSecureLogin();
      }}
    >
      <div
        className="rms-panel"
        style={{
          width: isMobile ? "100%" : "min(440px, 92vw)",
          overflow: "hidden",
        }}
      >
        <div className="rms-title" style={{ fontSize: isMobile ? 12 : 14 }}>Secure Unlock / Change User</div>

        <div style={{ padding: isMobile ? 12 : 18 }}>
          <div style={{ marginBottom: isMobile ? 12 : 16, color: "#334155", fontSize: isMobile ? 12 : 14 }}>
            Sign in with cashier, supervisor, manager, or admin credentials to continue.
          </div>

          <form onSubmit={handleSecureLogin} style={{ display: "grid", gap: isMobile ? 10 : 12 }}>
            <input
              className="rms-input"
              type="email"
              placeholder="Email"
              value={secureEmail}
              onChange={(e) => setSecureEmail(e.target.value)}
              required
              style={{ fontSize: isMobile ? 13 : 14 }}
            />

            <input
              className="rms-input"
              type="password"
              placeholder="Password"
              value={securePassword}
              onChange={(e) => setSecurePassword(e.target.value)}
              required
              style={{ fontSize: isMobile ? 13 : 14 }}
            />

            {secureError && (
              <div
                style={{
                  background: "#fef2f2",
                  border: "1px solid #fecaca",
                  borderRadius: 8,
                  padding: isMobile ? "8px 10px" : "10px 12px",
                  fontSize: isMobile ? 12 : 13,
                  color: "#b42318",
                }}
              >
                {secureError}
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: isMobile ? 8 : 10 }}>
              <button
                type="submit"
                disabled={secureLoading}
                style={{
                  ...getActionButtonStyle(isMobile),
                  minHeight: isMobile ? 38 : 46,
                  opacity: secureLoading ? 0.7 : 1,
                  cursor: secureLoading ? "not-allowed" : "pointer",
                }}
              >
                {secureLoading ? "Signing In..." : "Sign In"}
              </button>

              <button
                type="button"
                style={getUtilityButtonStyle(isMobile)}
                onClick={closeSecureLogin}
              >
                Cancel
              </button>
            </div>

            <button
              type="button"
              style={{
                ...getUtilityButtonStyle(isMobile),
                borderColor: "#7a1f1f",
                color: "#fecaca",
                minHeight: isMobile ? 38 : 48,
              }}
              onClick={() => {
                clearSession();
                closeSecureLogin();
                onNavigate?.("login");
              }}
            >
              Full Logout
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}