import { useEffect, useMemo, useState } from "react";
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

function readResetContext() {
  const url = new URL(window.location.href);
  const hash = window.location.hash || "";
  const hashMatch = hash.match(/#\/reset-password\/?([^?]*)?(?:\?(.*))?$/);

  let token = url.searchParams.get("token") || "";
  let email = url.searchParams.get("email") || "";

  if (hashMatch) {
    const hashToken = hashMatch[1] || "";
    const hashQuery = new URLSearchParams(hashMatch[2] || "");
    if (!token && hashToken) token = decodeURIComponent(hashToken);
    if (!email) email = hashQuery.get("email") || "";
    if (!token) token = hashQuery.get("token") || "";
  }

  return { token, email };
}

export default function ResetPassword({ onNavigate }) {
  const initialContext = useMemo(() => readResetContext(), []);
  const [resetToken] = useState(initialContext.token);
  const [email, setEmail] = useState(initialContext.email);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const validate = () => {
    if (!resetToken) {
      setError("Invalid password reset link.");
      return false;
    }
    if (!email.trim()) {
      setError("Reset email is required.");
      return false;
    }
    if (!password) {
      setError("Please enter a new password.");
      return false;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return false;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return false;
    }
    if (!/[A-Z]/.test(password)) {
      setError("Password must contain an uppercase letter.");
      return false;
    }
    if (!/[a-z]/.test(password)) {
      setError("Password must contain a lowercase letter.");
      return false;
    }
    if (!/[0-9]/.test(password)) {
      setError("Password must contain a number.");
      return false;
    }
    setError("");
    return true;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (loading || !validate()) return;

    setLoading(true);
    try {
      const response = await authAPI.resetPassword({
        email: email.trim(),
        token: resetToken,
        new_password: password,
      });
      setMessage(response?.message || "Your password has been reset. Please sign in with your new password.");
      setPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err.message || "Reset failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#eef2ff", display: "flex", alignItems: "center", justifyContent: "center", padding: isMobile ? 12 : 20, fontFamily: "Tahoma, Verdana, Arial, sans-serif" }}>
      <div style={{ width: "100%", maxWidth: 520, background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 12, padding: isMobile ? 18 : 24, boxShadow: "0 18px 40px rgba(15, 23, 42, 0.12)" }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: isMobile ? 22 : 26, fontWeight: 800, color: "#0f172a", marginBottom: 8 }}>Create a new password</div>
          <div style={{ fontSize: isMobile ? 12 : 14, color: "#475569", lineHeight: 1.7 }}>Set a secure password for your Smartlynx account.</div>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={getLabelStyle(isMobile)}>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin@store.ke" style={getFieldStyle(isMobile)} required />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={getLabelStyle(isMobile)}>New Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Strong password" style={getFieldStyle(isMobile)} />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={getLabelStyle(isMobile)}>Confirm Password</label>
            <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Repeat password" style={getFieldStyle(isMobile)} />
          </div>

          {error ? <div style={{ color: "#b42318", background: "#fef2f2", borderRadius: 8, padding: "10px 12px", marginBottom: 16 }}>{error}</div> : null}
          {message ? <div style={{ color: "#14532d", background: "#dcfce7", borderRadius: 8, padding: "10px 12px", marginBottom: 16 }}>{message}</div> : null}

          <button type="submit" disabled={loading} style={{ width: "100%", minHeight: 44, background: loading ? "#94a3b8" : "#0f4ad3", border: "1px solid #0f4ad3", borderRadius: 8, color: "#fff", fontWeight: 700, letterSpacing: ".05em", cursor: loading ? "not-allowed" : "pointer" }}>
            {loading ? "Saving..." : "Reset password"}
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
