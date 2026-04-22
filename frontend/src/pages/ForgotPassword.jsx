import { useEffect, useState } from "react";
import { authAPI } from "../api/client";

const getFieldStyle = (isMobile) => ({
  width: "100%",
  border: "1px solid #92a8c9",
  background: "#ffffff",
  borderRadius: 6,
  color: "#111827",
  fontFamily: "Tahoma, Verdana, Arial, sans-serif",
  fontSize: isMobile ? 13 : 14,
  padding: isMobile ? "9px 10px" : "11px 12px",
  outline: "none",
  boxSizing: "border-box",
});

const getLabelStyle = (isMobile) => ({
  fontSize: isMobile ? 10 : 11,
  color: "#334155",
  fontWeight: 700,
  letterSpacing: ".05em",
  display: "block",
  marginBottom: 6,
  textTransform: "uppercase",
});

export default function ForgotPassword({ onNavigate }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (loading) return;

    setError("");
    setMessage("");
    setLoading(true);

    try {
      const response = await authAPI.forgotPassword({ email: email.trim() });
      setMessage(response?.message || "If an account with that email exists, a reset link will be sent.");
    } catch (err) {
      setError(err.message || "Unable to request password reset");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#eff6ff", display: "flex", alignItems: "center", justifyContent: "center", padding: isMobile ? 12 : 20, fontFamily: "Tahoma, Verdana, Arial, sans-serif" }}>
      <div style={{ width: "100%", maxWidth: 520, background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 12, padding: isMobile ? 18 : 24, boxShadow: "0 18px 40px rgba(15, 23, 42, 0.12)" }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: isMobile ? 22 : 26, fontWeight: 800, color: "#0f172a", marginBottom: 8 }}>Reset your password</div>
          <div style={{ fontSize: isMobile ? 12 : 14, color: "#475569", lineHeight: 1.7 }}>Enter the email address used for your Smartlynx account.</div>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={getLabelStyle(isMobile)}>Email</label>
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="admin@store.ke" required style={getFieldStyle(isMobile)} />
          </div>

          {error ? <div style={{ color: "#b42318", background: "#fef2f2", borderRadius: 8, padding: "10px 12px", marginBottom: 16 }}>{error}</div> : null}
          {message ? <div style={{ color: "#14532d", background: "#dcfce7", borderRadius: 8, padding: "10px 12px", marginBottom: 16 }}>{message}</div> : null}

          <button type="submit" disabled={loading} style={{ width: "100%", minHeight: 44, background: loading ? "#94a3b8" : "#0f4ad3", border: "1px solid #0f4ad3", borderRadius: 8, color: "#fff", fontWeight: 700, letterSpacing: ".05em", cursor: loading ? "not-allowed" : "pointer" }}>
            {loading ? "Sending..." : "Send reset link"}
          </button>
        </form>

        <div style={{ marginTop: 18, display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <button type="button" onClick={() => onNavigate("login")} style={{ flex: 1, border: "1px solid #cbd5e1", borderRadius: 8, padding: isMobile ? "10px 12px" : "12px 14px", background: "#ffffff", color: "#475569", fontWeight: 700, cursor: "pointer" }}>
            Back to login
          </button>
          <button type="button" onClick={() => onNavigate("register")} style={{ flex: 1, border: "none", borderRadius: 8, padding: isMobile ? "10px 12px" : "12px 14px", background: "#eef2ff", color: "#0f4ad3", fontWeight: 700, cursor: "pointer" }}>
            Create store
          </button>
        </div>
      </div>
    </div>
  );
}
