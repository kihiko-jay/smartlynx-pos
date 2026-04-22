import { useState, useEffect } from "react";
import { productsAPI } from "../../../../api/client";
import { shellStyles } from "../../styles";
import { Section } from "../../UIComponents";

export default function SupplierForm({ supplier, onSave, onCancel }) {
  const [form, setForm] = useState({
    name: "",
    contact_name: "",
    phone: "",
    email: "",
    address: "",
    kra_pin: "",
  });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    if (supplier) {
      setForm(supplier);
    }
  }, [supplier]);

  const validateForm = () => {
    const newErrors = {};
    if (!form.name || form.name.trim() === "") {
      newErrors.name = "Supplier name is required";
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm()) return;

    setLoading(true);
    try {
      if (supplier?.id) {
        await productsAPI.update(supplier.id, form);
      } else {
        await productsAPI.createSupplier(form);
      }
      onSave();
    } catch (e) {
      setErrors({ _form: e.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Section title={supplier?.id ? "Edit Supplier" : "Create Supplier"}>
      <form onSubmit={handleSubmit}>
        <div style={{ padding: isMobile ? "12px 16px" : "16px 20px", display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(2, 1fr)", gap: 12 }}>
          <div>
            <label style={{ display: "block", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>
              Name <span style={{ color: "#dc2626" }}>*</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              style={{
                ...shellStyles.searchInput,
                borderColor: errors.name ? "#dc2626" : "#92a8c9",
                fontSize: 11,
              }}
              placeholder="Supplier name"
              disabled={loading}
            />
            {errors.name && <div style={{ fontSize: 10, color: "#dc2626", marginTop: 2 }}>{errors.name}</div>}
          </div>
          <div>
            <label style={{ display: "block", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>
              Contact Name
            </label>
            <input
              type="text"
              value={form.contact_name}
              onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
              style={{ ...shellStyles.searchInput, fontSize: 11 }}
              placeholder="Contact person"
              disabled={loading}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>
              Phone
            </label>
            <input
              type="tel"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              style={{ ...shellStyles.searchInput, fontSize: 11 }}
              placeholder="Phone number"
              disabled={loading}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>
              Email
            </label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              style={{ ...shellStyles.searchInput, fontSize: 11 }}
              placeholder="Email address"
              disabled={loading}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>
              KRA PIN
            </label>
            <input
              type="text"
              value={form.kra_pin}
              onChange={(e) => setForm({ ...form, kra_pin: e.target.value })}
              style={{ ...shellStyles.searchInput, fontSize: 11 }}
              placeholder="KRA PIN"
              disabled={loading}
            />
          </div>
          <div style={{ gridColumn: isMobile ? "1" : "1 / -1" }}>
            <label style={{ display: "block", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>
              Address
            </label>
            <textarea
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
              style={{ ...shellStyles.searchInput, fontSize: 11, minHeight: 60, resize: "vertical" }}
              placeholder="Supplier address"
              disabled={loading}
            />
          </div>
        </div>

        {errors._form && (
          <div style={{ padding: "10px 16px", background: "#fee2e2", color: "#dc2626", fontSize: 11, borderTop: "1px solid #cbd5e1" }}>
            {errors._form}
          </div>
        )}

        <div
          style={{
            display: "flex",
            gap: 8,
            justifyContent: "flex-end",
            padding: "10px 12px",
            borderTop: "1px solid #cbd5e1",
            background: "#f9fafb",
          }}
        >
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            style={{ ...shellStyles.smallButton(isMobile), background: "#6b7280" }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            style={shellStyles.primaryButton(isMobile)}
          >
            {loading ? "Saving..." : supplier?.id ? "Save" : "Create"}
          </button>
        </div>
      </form>
    </Section>
  );
}
