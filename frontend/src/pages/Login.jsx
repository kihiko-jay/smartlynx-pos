import { useEffect, useState } from "react";
import { authAPI, saveSession, sessionHelpers } from "../api/client";

const isElectron = typeof window !== "undefined" && !!window.electron?.app?.isElectron;
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";
const DEMO_USERNAME = DEMO_MODE ? import.meta.env.VITE_DEMO_USERNAME || "admin" : "";
const DEMO_EMAIL = DEMO_MODE ? import.meta.env.VITE_DEMO_EMAIL || "admin@dukapos.ke" : "";
const DEMO_PASSWORD = DEMO_MODE ? import.meta.env.VITE_DEMO_PASSWORD || "admin1234" : "";

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

export default function Login({ onLogin, onNavigate, bootError = "", onClearBootError }) {
  const [username, setUsername] = useState(DEMO_USERNAME || DEMO_EMAIL); // Can be username or email
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [error, setError] = useState(bootError);
  const [loading, setLoading] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);
  const [apiBase, setApiBase] = useState("");
  const [isConnectionError, setIsConnectionError] = useState(false);
  const [inputType, setInputType] = useState("text"); // For showing username/email hint

  useEffect(() => {
    setError(bootError || "");
  }, [bootError]);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    // Load current server address on component mount (Electron only)
    if (isElectron) {
      window.electron.config.get("apiBase").then((addr) => {
        setApiBase(addr || "");
      }).catch(() => {
        setApiBase("");
      });
    }
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (loading) return;

    setError("");
    setIsConnectionError(false);
    onClearBootError?.();
    setLoading(true);

    try {
      // Use 'username' field instead of 'email' - accepts both username and email
      const data = await authAPI.login(username.trim(), password);

      await sessionHelpers.saveTokens({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
      });

      const session = {
        id: data.employee_id,
        name: data.full_name,
        role: data.role,
        terminal_id: data.terminal_id,
        store_name: data.store_name,
        store_location: data.store_location,
      };

      await saveSession(session);

      if (isElectron) {
        try {
          await window.electron.config.set("session", session);
        } catch {
          // ignore electron config write failure
        }
      }

      onLogin(data);
    } catch (err) {
      const errorMsg = err.message || "Login failed";
      
      // Detect if this is a connection error vs auth error
      const isConnError = 
        errorMsg.includes("Failed to fetch") ||
        errorMsg.includes("Cannot reach") ||
        errorMsg.includes("unreachable") ||
        errorMsg.includes("ECONNREFUSED") ||
        errorMsg.includes("ENOTFOUND") ||
        errorMsg.includes("timed out");
      
      setIsConnectionError(isConnError);
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenSettings = async () => {
    if (isElectron && window.electron?.ui?.openSettings) {
      try {
        await window.electron.ui.openSettings();
      } catch (err) {
        console.error("Failed to open settings:", err);
      }
    }
  };

  const handleReopenSetup = async () => {
    if (isElectron && window.electron?.ui?.reopenSetup) {
      try {
        await window.electron.ui.reopenSetup();
      } catch (err) {
        console.error("Failed to reopen setup:", err);
      }
    }
  };

  // Detect if input looks like an email to show appropriate hint
  const isEmailInput = username.includes("@") && username.includes(".");
  
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#d7dee8",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "Tahoma, Verdana, Arial, sans-serif",
        padding: isMobile ? 12 : 20,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 920,
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr" : "1.1fr 0.9fr",
          border: "1px solid #9eb2ce",
          borderRadius: isMobile ? 8 : 12,
          overflow: "hidden",
          boxShadow: "0 18px 40px rgba(15, 23, 42, 0.16)",
          background: "#f6f8fb",
        }}
      >
        {!isMobile && (
          <div
            style={{
              background: "linear-gradient(180deg, #0d58d2 0%, #04389c 100%)",
              color: "#fff",
              padding: "44px 40px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              minHeight: 560,
            }}
          >
            <div>
              <div style={{ fontSize: 32, fontWeight: 800, letterSpacing: ".02em", marginBottom: 8 }}>
                Smartlynx POS
              </div>
              <div style={{ fontSize: 13, opacity: 0.9, letterSpacing: ".08em", textTransform: "uppercase" }}>
                Store Operations System
              </div>
            </div>

            <div>
              <div style={{ fontSize: 34, fontWeight: 800, lineHeight: 1.15, marginBottom: 16 }}>
                Fast retail checkout.
                <br />
                Back office control.
                <br />
                Built for real stores.
              </div>

              <div style={{ fontSize: 15, lineHeight: 1.7, maxWidth: 420, color: "rgba(255,255,255,0.92)" }}>
                Sign in to access POS sales, inventory, reports, procurement, sync monitoring, and store administration.
              </div>
            </div>

            <div style={{ borderTop: "1px solid rgba(255,255,255,0.2)", paddingTop: 18, fontSize: 12, lineHeight: 1.8, color: "rgba(255,255,255,0.9)" }}>
              <div>• Cashier access for fast checkout</div>
              <div>• Supervisor and admin back office tools</div>
              <div>• M-Pesa, offline queue, receipts, audit trail</div>
            </div>
          </div>
        )}

        <div
          style={{
            background: "linear-gradient(180deg, #f6f8fb 0%, #edf2f8 100%)",
            padding: isMobile ? "20px 16px" : "32px 30px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
          }}
        >
          <div style={{ background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: isMobile ? 8 : 12, overflow: "hidden" }}>
            <div style={{ background: "linear-gradient(180deg, #155eef 0%, #003eb3 100%)", color: "#fff", padding: isMobile ? "10px 12px" : "12px 16px", fontSize: isMobile ? 11 : 12, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase" }}>
              Staff Login
            </div>

            <div style={{ padding: isMobile ? 14 : 20 }}>
              <div style={{ marginBottom: isMobile ? 14 : 20 }}>
                <div style={{ fontSize: isMobile ? 22 : 28, fontWeight: 800, color: "#111827", marginBottom: 6 }}>
                  Welcome back
                </div>
                <div style={{ fontSize: isMobile ? 12 : 14, color: "#64748b", lineHeight: 1.6 }}>
                  Enter your username or email and password to continue.
                </div>
              </div>

              {isElectron && apiBase && !error && (
                <div style={{ background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: 6, padding: "8px 10px", marginBottom: 14, fontSize: 11, color: "#0369a1" }}>
                  <strong>Server:</strong> <code style={{ fontSize: 10, fontFamily: "monospace" }}>{apiBase}</code>
                </div>
              )}

              <form onSubmit={handleSubmit}>
                <div style={{ marginBottom: 14 }}>
                  <label style={getLabelStyle(isMobile)}>
                    Username or Email
                    {isEmailInput && username && (
                      <span style={{ fontSize: 10, fontWeight: "normal", marginLeft: 8, color: "#6b7280" }}>
                        (using email)
                      </span>
                    )}
                  </label>
                  <input 
                    type="text" 
                    value={username} 
                    onChange={(e) => setUsername(e.target.value)} 
                    autoComplete="username" 
                    required 
                    placeholder="e.g., john_doe or john@example.com"
                    style={getFieldStyle(isMobile)} 
                  />
                  <div style={{ fontSize: 10, color: "#6b7280", marginTop: 4, display: "flex", gap: 8 }}>
                    <span>💡 Tip: Use your username (e.g., "admin") OR email address</span>
                  </div>
                </div>

                <div style={{ marginBottom: 16 }}>
                  <label style={getLabelStyle(isMobile)}>Password</label>
                  <input 
                    type="password" 
                    value={password} 
                    onChange={(e) => setPassword(e.target.value)} 
                    autoComplete="current-password" 
                    required 
                    style={getFieldStyle(isMobile)} 
                  />
                </div>

                {error ? (
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ color: "#b42318", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 12px", marginBottom: 12, fontSize: 13 }}>
                      {isConnectionError 
                        ? "Cannot reach SmartlynX server. Check the server address below and whether the backend is running."
                        : error
                      }
                    </div>
                    
                    {isConnectionError && isElectron && (
                      <div style={{ backgroundColor: "#f5f3ff", border: "1px solid #e9d5ff", borderRadius: 6, padding: "12px", fontSize: 12, lineHeight: 1.5 }}>
                        <div style={{ fontWeight: 600, color: "#6b21a8", marginBottom: 8 }}>
                          💡 Troubleshooting Connection Issues
                        </div>
                        
                        {apiBase && (
                          <div style={{ marginBottom: 8, padding: "8px", background: "#f3f0ff", borderRadius: 4, fontFamily: "monospace", fontSize: 11, color: "#333", wordBreak: "break-all" }}>
                            <strong>Configured Server:</strong> {apiBase}
                          </div>
                        )}
                        
                        <div style={{ color: "#333", marginBottom: 8 }}>
                          • Verify the server address is correct (shown above)<br />
                          • Check that the SmartlynX backend is running<br />
                          • Confirm your network connection is active<br />
                          • Try using your username instead of email (or vice versa)
                        </div>
                        
                        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                          <button
                            type="button"
                            onClick={handleOpenSettings}
                            style={{
                              flex: 1,
                              padding: "8px 10px",
                              background: "#7c3aed",
                              color: "#fff",
                              border: "none",
                              borderRadius: 4,
                              fontSize: 12,
                              fontWeight: 600,
                              cursor: "pointer",
                            }}
                          >
                            ⚙ Open Settings
                          </button>
                          <button
                            type="button"
                            onClick={handleReopenSetup}
                            style={{
                              flex: 1,
                              padding: "8px 10px",
                              background: "#06b6d4",
                              color: "#fff",
                              border: "none",
                              borderRadius: 4,
                              fontSize: 12,
                              fontWeight: 600,
                              cursor: "pointer",
                            }}
                          >
                            🔧 Run Setup Wizard
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ) : null}

                <button
                  type="submit"
                  disabled={loading}
                  style={{
                    width: "100%",
                    minHeight: 44,
                    background: loading ? "#94a3b8" : "#0f4ad3",
                    border: "1px solid #0f4ad3",
                    borderRadius: 8,
                    color: "#fff",
                    fontWeight: 700,
                    letterSpacing: ".05em",
                    cursor: loading ? "not-allowed" : "pointer",
                  }}
                >
                  {loading ? "Signing in..." : "Sign in"}
                </button>
              </form>

              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 18, flexWrap: "wrap" }}>
                <button type="button" onClick={() => onNavigate("forgot-password")} style={{ background: "transparent", border: "none", color: "#0f4ad3", fontWeight: 700, cursor: "pointer", padding: 0 }}>
                  Forgot password?
                </button>
                <button type="button" onClick={() => onNavigate("register")} style={{ background: "transparent", border: "none", color: "#0f4ad3", fontWeight: 700, cursor: "pointer", padding: 0 }}>
                  Create store
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}