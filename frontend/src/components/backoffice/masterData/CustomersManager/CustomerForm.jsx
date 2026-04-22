import { useState, useEffect } from "react";
import { customersAPI } from "../../../../api/client";
import { shellStyles } from "../../styles";
import { Section } from "../../UIComponents";

export default function CustomerForm({ customer, onSave, onCancel }) {
  const [form, setForm] = useState({
    name: "",
    phone: "",
    email: "",
    credit_limit: "0",
    notes: "",
  });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    if (customer) {
      setForm({
        name: customer.name,
        phone: customer.phone || "",
        email: customer.email || "",
        credit_limit: String(customer.credit_limit || "0"),
        notes: customer.notes || "",
      });
    }
  }, [customer]);

  const validateForm = () => {
    const newErrors = {};
    if (!form.name || form.name.trim() === "") {
      newErrors.name = "Customer name is required";
    }
    if (parseFloat(form.credit_limit) < 0) {
      newErrors.credit_limit = "Credit limit must not be negative";
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm()) return;

    setLoading(true);
    try {
      const payload = {
        name: form.name,
        phone: form.phone || null,
        email: form.email || null,
        credit_limit: parseFloat(form.credit_limit),
        notes: form.notes || null,
      };

      if (customer?.id) {
        await customersAPI.update(customer.id, payload);
      } else {
        await customersAPI.create(payload);
      }
      onSave();
    } catch (e) {
      setErrors({ _form: e.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Section title={customer?.id ? "Edit Customer" : "Create Customer"}>
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
              placeholder="Customer name"
              disabled={loading}
            />
            {errors.name && <div style={{ fontSize: 10, color: "#dc2626", marginTop: 2 }}>{errors.name}</div>}
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
              Credit Limit (KES)
            </label>
            <input
              type="number"
              value={form.credit_limit}
              onChange={(e) => setForm({ ...form, credit_limit: e.target.value })}
              style={{
                ...shellStyles.searchInput,
                borderColor: errors.credit_limit ? "#dc2626" : "#92a8c9",
                fontSize: 11,
              }}
              placeholder="0.00"
              disabled={loading}
              step="0.01"
              min="0"
            />
            {errors.credit_limit && <div style={{ fontSize: 10, color: "#dc2626", marginTop: 2 }}>{errors.credit_limit}</div>}
          </div>
          <div style={{ gridColumn: isMobile ? "1" : "1 / -1" }}>
            <label style={{ display: "block", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>
              Notes
            </label>
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              style={{ ...shellStyles.searchInput, fontSize: 11, minHeight: 60, resize: "vertical" }}
              placeholder="Customer notes"
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
            {loading ? "Saving..." : customer?.id ? "Save" : "Create"}
          </button>
        </div>
      </form>
    </Section>
  );
}
