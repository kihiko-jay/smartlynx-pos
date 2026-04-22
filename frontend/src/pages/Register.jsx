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

export default function Register({ onNavigate }) {
  const [formData, setFormData] = useState({
    store_name: "",
    store_location: "",
    store_email: "",
    store_phone: "",
    store_kra_pin: "",
    admin_full_name: "",
    admin_email: "",
    admin_password: "",
    admin_password_confirm: "",
  });
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const validate = () => {
    const fieldErrors = {};

    if (!formData.store_name.trim()) fieldErrors.store_name = "Store name is required";
    if (!formData.admin_full_name.trim()) fieldErrors.admin_full_name = "Admin full name is required";
    if (!formData.admin_email.trim()) fieldErrors.admin_email = "Admin email is required";
    if (!formData.admin_password) fieldErrors.admin_password = "Password is required";
    if (formData.admin_password !== formData.admin_password_confirm) fieldErrors.admin_password_confirm = "Passwords do not match";
    if (formData.admin_password && formData.admin_password.length < 8) fieldErrors.admin_password = "Password must be at least 8 characters";
    if (formData.admin_password && !/[A-Z]/.test(formData.admin_password)) fieldErrors.admin_password = "Password must contain an uppercase letter";
    if (formData.admin_password && !/[a-z]/.test(formData.admin_password)) fieldErrors.admin_password = "Password must contain a lowercase letter";
    if (formData.admin_password && !/[0-9]/.test(formData.admin_password)) fieldErrors.admin_password = "Password must contain a number";

    setErrors(fieldErrors);
    return Object.keys(fieldErrors).length === 0;
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => ({ ...prev, [name]: "", submit: "" }));
    setMessage("");
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (loading) return;
    setMessage("");
    if (!validate()) return;

    setLoading(true);
    try {
      const response = await authAPI.register({
        store_name: formData.store_name.trim(),
        store_location: formData.store_location.trim() || undefined,
        store_email: formData.store_email.trim() || undefined,
        store_phone: formData.store_phone.trim() || undefined,
        store_kra_pin: formData.store_kra_pin.trim() || undefined,
        admin_full_name: formData.admin_full_name.trim(),
        admin_email: formData.admin_email.trim(),
        admin_password: formData.admin_password,
      });

      setMessage(response?.message || "Registration successful. You can now sign in.");
      setFormData({
        store_name: "",
        store_location: "",
        store_email: "",
        store_phone: "",
        store_kra_pin: "",
        admin_full_name: "",
        admin_email: "",
        admin_password: "",
        admin_password_confirm: "",
      });
    } catch (error) {
      setErrors({ submit: error.message || "Registration failed" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#eef2ff", display: "flex", alignItems: "center", justifyContent: "center", padding: isMobile ? 12 : 20, fontFamily: "Tahoma, Verdana, Arial, sans-serif" }}>
      <div style={{ width: "100%", maxWidth: 980, display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1.1fr 0.9fr", gap: 20 }}>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", background: "linear-gradient(180deg, #0b4bc3 0%, #0a3c8f 100%)", color: "#fff", borderRadius: 12, padding: isMobile ? "24px 20px" : "40px 36px", minHeight: 540 }}>
          <div>
            <div style={{ fontSize: isMobile ? 28 : 34, fontWeight: 800, marginBottom: 10 }}>Launch your store.</div>
            <div style={{ fontSize: isMobile ? 13 : 14, lineHeight: 1.7, opacity: 0.92 }}>
              Register your store, create the first admin account, and start selling with Smartlynx.
            </div>
          </div>

          <div style={{ fontSize: isMobile ? 13 : 14, lineHeight: 1.8 }}>
            <div>• Store registration with free trial</div>
            <div>• Admin user onboarding</div>
            <div>• Inventory, POS, and back office</div>
            <div>• Secure employee roles and access</div>
          </div>
        </div>

        <div style={{ background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 12, padding: isMobile ? 16 : 24, boxShadow: "0 14px 30px rgba(15, 23, 42, 0.08)" }}>
          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: isMobile ? 22 : 26, fontWeight: 800, color: "#111827" }}>Create your store</div>
            <div style={{ fontSize: isMobile ? 12 : 13, color: "#64748b", lineHeight: 1.7 }}>
              Enter your store details and the first admin account.
            </div>
          </div>

          <form onSubmit={handleSubmit}>
            <div style={{ display: "grid", gap: 14 }}>
              <div>
                <label style={getLabelStyle(isMobile)}>Store Name</label>
                <input name="store_name" value={formData.store_name} onChange={handleChange} placeholder="e.g. Nakuru Supermart" required style={getFieldStyle(isMobile)} />
                {errors.store_name ? <div style={{ color: "#b42318", fontSize: 12, marginTop: 6 }}>{errors.store_name}</div> : null}
              </div>

              <div>
                <label style={getLabelStyle(isMobile)}>Store Location</label>
                <input name="store_location" value={formData.store_location} onChange={handleChange} placeholder="e.g. Nkr-Green Market" style={getFieldStyle(isMobile)} />
              </div>

              <div>
                <label style={getLabelStyle(isMobile)}>Store Email</label>
                <input name="store_email" value={formData.store_email} onChange={handleChange} type="email" placeholder="store@example.com" style={getFieldStyle(isMobile)} />
              </div>

              <div style={{ display: isMobile ? "block" : "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  <label style={getLabelStyle(isMobile)}>Store Phone</label>
                  <input name="store_phone" value={formData.store_phone} onChange={handleChange} placeholder="e.g. +254700123456" style={getFieldStyle(isMobile)} />
                </div>
                <div>
                  <label style={getLabelStyle(isMobile)}>KRA PIN</label>
                  <input name="store_kra_pin" value={formData.store_kra_pin} onChange={handleChange} placeholder="e.g. A001234567B" style={getFieldStyle(isMobile)} />
                </div>
              </div>

              <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid #e2e8f0" }}>
                <div style={{ fontSize: isMobile ? 12 : 13, fontWeight: 700, color: "#0f172a", marginBottom: 10 }}>Admin account</div>

                <div>
                  <label style={getLabelStyle(isMobile)}>Full Name</label>
                  <input name="admin_full_name" value={formData.admin_full_name} onChange={handleChange} placeholder="e.g. Jane Mwangi" required style={getFieldStyle(isMobile)} />
                  {errors.admin_full_name ? <div style={{ color: "#b42318", fontSize: 12, marginTop: 6 }}>{errors.admin_full_name}</div> : null}
                </div>

                <div>
                  <label style={getLabelStyle(isMobile)}>Email</label>
                  <input name="admin_email" value={formData.admin_email} onChange={handleChange} type="email" placeholder="admin@store.ke" required style={getFieldStyle(isMobile)} />
                  {errors.admin_email ? <div style={{ color: "#b42318", fontSize: 12, marginTop: 6 }}>{errors.admin_email}</div> : null}
                </div>

                <div style={{ display: isMobile ? "block" : "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 14 }}>
                  <div>
                    <label style={getLabelStyle(isMobile)}>Password</label>
                    <input name="admin_password" value={formData.admin_password} onChange={handleChange} type="password" required style={getFieldStyle(isMobile)} />
                    {errors.admin_password ? <div style={{ color: "#b42318", fontSize: 12, marginTop: 6 }}>{errors.admin_password}</div> : null}
                  </div>
                  <div>
                    <label style={getLabelStyle(isMobile)}>Confirm Password</label>
                    <input name="admin_password_confirm" value={formData.admin_password_confirm} onChange={handleChange} type="password" required style={getFieldStyle(isMobile)} />
                    {errors.admin_password_confirm ? <div style={{ color: "#b42318", fontSize: 12, marginTop: 6 }}>{errors.admin_password_confirm}</div> : null}
                  </div>
                </div>
              </div>

              {errors.submit ? <div style={{ color: "#b42318", background: "#fef2f2", borderRadius: 8, padding: "10px 12px" }}>{errors.submit}</div> : null}
              {message ? <div style={{ color: "#14532d", background: "#dcfce7", borderRadius: 8, padding: "10px 12px" }}>{message}</div> : null}

              <button type="submit" disabled={loading} style={{ width: "100%", minHeight: 44, background: loading ? "#94a3b8" : "#0f4ad3", border: "1px solid #0f4ad3", borderRadius: 8, color: "#fff", fontWeight: 700, letterSpacing: ".05em", cursor: loading ? "not-allowed" : "pointer" }}>
                {loading ? "Creating store..." : "Create store"}
              </button>
            </div>
          </form>

          <div style={{ marginTop: 18, textAlign: "center" }}>
            <button type="button" onClick={() => onNavigate("login")} style={{ background: "transparent", border: "none", color: "#0f4ad3", fontWeight: 700, cursor: "pointer" }}>
              Already have an account? Sign in
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
