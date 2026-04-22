import { useState, useEffect } from "react";
import { productsAPI } from "../../../../api/client";
import { shellStyles } from "../../styles";
import { Section } from "../../UIComponents";

export default function ProductForm({
  product,
  categories,
  suppliers,
  onSave,
  onCancel,
}) {
  const [form, setForm] = useState({
    sku: "",
    name: "",
    description: "",
    barcode: "",
    itemcode: "",
    selling_price: "",
    cost_price: "",
    category_id: null,
    supplier_id: null,
    stock_quantity: "0",
    reorder_level: "10",
    unit: "piece",
    tax_code: "B",
    vat_exempt: false,
  });

  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (product) {
      setForm({
        ...form,
        ...product,
        category_id: product.category_id || null,
        supplier_id: product.supplier_id || null,
      });
    }
  }, [product]);

  const validateForm = () => {
    const newErrors = {};

    if (!form.sku || form.sku.trim() === "") {
      newErrors.sku = "SKU is required";
    }

    if (!form.name || form.name.trim() === "") {
      newErrors.name = "Product name is required";
    }

    if (!form.selling_price || parseFloat(form.selling_price) <= 0) {
      newErrors.selling_price = "Selling price must be greater than 0";
    }

    if (form.cost_price && parseFloat(form.cost_price) < 0) {
      newErrors.cost_price = "Cost price must not be negative";
    }

    if (parseFloat(form.stock_quantity) < 0) {
      newErrors.stock_quantity = "Stock quantity must not be negative";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setLoading(true);
    try {
      const payload = {
        ...form,
        selling_price: parseFloat(form.selling_price),
        cost_price: form.cost_price ? parseFloat(form.cost_price) : null,
        stock_quantity: parseInt(form.stock_quantity),
        reorder_level: parseInt(form.reorder_level),
        category_id: form.category_id || null,
        supplier_id: form.supplier_id || null,
      };

      if (product?.id) {
        await productsAPI.update(product.id, payload);
      } else {
        await productsAPI.create(payload);
      }

      onSave();
    } catch (e) {
      setErrors({ _form: e.message });
    } finally {
      setLoading(false);
    }
  };

  const handleFieldChange = (field, value) => {
    setForm({ ...form, [field]: value });
    if (errors[field]) {
      setErrors({ ...errors, [field]: "" });
    }
  };

  const renderInput = (label, field, type = "text", placeholder = "") => {
    const error = errors[field];
    const value = form[field];

    return (
      <div style={{ marginBottom: 12 }}>
        <label
          style={{
            display: "block",
            fontSize: isMobile ? 10 : 12,
            fontWeight: 600,
            marginBottom: 4,
            color: "#334155",
          }}
        >
          {label}
          {["sku", "name", "selling_price"].includes(field) && (
            <span style={{ color: "#dc2626" }}>*</span>
          )}
        </label>
        <input
          type={type}
          value={value}
          onChange={(e) => handleFieldChange(field, e.target.value)}
          placeholder={placeholder}
          disabled={loading}
          style={{
            ...shellStyles.searchInput,
            borderColor: error ? "#dc2626" : "#92a8c9",
            background: error ? "#fee2e2" : "#fff",
            fontSize: isMobile ? 11 : 12,
          }}
        />
        {error && (
          <div style={{ fontSize: 10, color: "#dc2626", marginTop: 2 }}>{error}</div>
        )}
      </div>
    );
  };

  const renderSelect = (label, field, options) => {
    const error = errors[field];

    return (
      <div style={{ marginBottom: 12 }}>
        <label
          style={{
            display: "block",
            fontSize: isMobile ? 10 : 12,
            fontWeight: 600,
            marginBottom: 4,
            color: "#334155",
          }}
        >
          {label}
        </label>
        <select
          value={form[field] || ""}
          onChange={(e) =>
            handleFieldChange(
              field,
              e.target.value ? parseInt(e.target.value) : null
            )
          }
          disabled={loading}
          style={{
            ...shellStyles.searchInput,
            borderColor: error ? "#dc2626" : "#92a8c9",
            background: error ? "#fee2e2" : "#fff",
            fontSize: isMobile ? 11 : 12,
          }}
        >
          <option value="">-- Select --</option>
          {options.map((opt) => (
            <option key={opt.id} value={opt.id}>
              {opt.name}
            </option>
          ))}
        </select>
        {error && (
          <div style={{ fontSize: 10, color: "#dc2626", marginTop: 2 }}>{error}</div>
        )}
      </div>
    );
  };

  return (
    <Section
      title={product?.id ? "Edit Product" : "Create Product"}
      style={{ maxHeight: "80vh", overflowY: "auto" }}
    >
      <form onSubmit={handleSubmit}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr" : "repeat(2, 1fr)",
            gap: 16,
            padding: isMobile ? "12px 16px" : "16px 20px",
          }}
        >
          {/* Left column */}
          <div>
            {renderInput("SKU", "sku", "text", "e.g., SKU-001")}
            {renderInput("Product Name", "name", "text", "Product name")}
            {renderInput("Barcode", "barcode", "text", "Optional barcode")}
            {renderInput("Item Code", "itemcode", "number", "Optional item code")}
            {renderSelect("Category", "category_id", categories)}
          </div>

          {/* Right column */}
          <div>
            {renderInput("Selling Price (KES)", "selling_price", "number", "0.00")}
            {renderInput("Cost Price (KES)", "cost_price", "number", "0.00")}
            {renderInput("Stock Quantity", "stock_quantity", "number", "0")}
            {renderInput("Reorder Level", "reorder_level", "number", "10")}
            {renderSelect("Supplier", "supplier_id", suppliers)}
          </div>
        </div>

        {/* Description - full width */}
        <div style={{ padding: isMobile ? "0 16px" : "0 20px", marginBottom: 12 }}>
          <label
            style={{
              display: "block",
              fontSize: isMobile ? 10 : 12,
              fontWeight: 600,
              marginBottom: 4,
              color: "#334155",
            }}
          >
            Description
          </label>
          <textarea
            value={form.description}
            onChange={(e) => handleFieldChange("description", e.target.value)}
            placeholder="Product description"
            disabled={loading}
            style={{
              ...shellStyles.searchInput,
              fontSize: isMobile ? 11 : 12,
              minHeight: 80,
              resize: "vertical",
            }}
          />
        </div>

        {/* Additional options - full width */}
        <div
          style={{
            padding: isMobile ? "12px 16px" : "16px 20px",
            borderTop: "1px solid #cbd5e1",
          }}
        >
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={form.vat_exempt}
                onChange={(e) => handleFieldChange("vat_exempt", e.target.checked)}
                disabled={loading}
              />
              <span style={{ fontSize: isMobile ? 11 : 12 }}>VAT Exempt</span>
            </label>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <label style={{ fontSize: isMobile ? 11 : 12 }}>Unit:</label>
              <select
                value={form.unit}
                onChange={(e) => handleFieldChange("unit", e.target.value)}
                disabled={loading}
                style={{
                  ...shellStyles.searchInput,
                  width: "auto",
                  fontSize: isMobile ? 11 : 12,
                }}
              >
                <option value="piece">Piece</option>
                <option value="box">Box</option>
                <option value="pack">Pack</option>
                <option value="kg">KG</option>
                <option value="liter">Liter</option>
              </select>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <label style={{ fontSize: isMobile ? 11 : 12 }}>Tax Code:</label>
              <select
                value={form.tax_code}
                onChange={(e) => handleFieldChange("tax_code", e.target.value)}
                disabled={loading}
                style={{
                  ...shellStyles.searchInput,
                  width: "auto",
                  fontSize: isMobile ? 11 : 12,
                }}
              >
                <option value="A">A - Standard</option>
                <option value="B">B - Standard</option>
                <option value="C">C - Exempt</option>
              </select>
            </div>
          </div>
        </div>

        {/* Form errors */}
        {errors._form && (
          <div
            style={{
              padding: "10px 16px",
              background: "#fee2e2",
              color: "#dc2626",
              fontSize: 12,
              borderTop: "1px solid #cbd5e1",
            }}
          >
            {errors._form}
          </div>
        )}

        {/* Buttons */}
        <div
          style={{
            display: "flex",
            gap: 8,
            justifyContent: "flex-end",
            padding: isMobile ? "10px 12px" : "12px 16px",
            borderTop: "1px solid #cbd5e1",
            background: "#f9fafb",
          }}
        >
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            style={{
              ...shellStyles.smallButton(isMobile),
              background: "#6b7280",
            }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            style={shellStyles.primaryButton(isMobile)}
          >
            {loading ? "Saving..." : product?.id ? "Save Changes" : "Create Product"}
          </button>
        </div>
      </form>
    </Section>
  );
}
