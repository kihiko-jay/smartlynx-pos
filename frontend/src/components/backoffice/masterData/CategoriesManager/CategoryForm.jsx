import { useState, useEffect } from "react";
import { productsAPI } from "../../../../api/client";
import { shellStyles } from "../../styles";
import { Section } from "../../UIComponents";

export default function CategoryForm({
  category,
  categories,
  onSave,
  onCancel,
}) {
  const [form, setForm] = useState({
    name: "",
    description: "",
    parent_id: null,
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
    if (category) {
      setForm({
        name: category.name,
        description: category.description || "",
        parent_id: category.parent_id || null,
      });
    }
  }, [category]);

  const validateForm = () => {
    const newErrors = {};

    if (!form.name || form.name.trim() === "") {
      newErrors.name = "Category name is required";
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
        name: form.name,
        description: form.description || null,
        parent_id: form.parent_id || null,
      };

      if (category?.id) {
        await productsAPI.update(category.id, payload);
      } else {
        await productsAPI.createCategory(payload);
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

  // Filter out current category from parent options
  const parentOptions = categories.filter(c => c.id !== category?.id);

  return (
    <Section title={category?.id ? "Edit Category" : "Create Category"}>
      <form onSubmit={handleSubmit}>
        <div style={{ padding: isMobile ? "12px 16px" : "16px 20px" }}>
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
              Category Name <span style={{ color: "#dc2626" }}>*</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => handleFieldChange("name", e.target.value)}
              placeholder="e.g., Electronics"
              disabled={loading}
              style={{
                ...shellStyles.searchInput,
                borderColor: errors.name ? "#dc2626" : "#92a8c9",
                background: errors.name ? "#fee2e2" : "#fff",
                fontSize: isMobile ? 11 : 12,
              }}
            />
            {errors.name && (
              <div style={{ fontSize: 10, color: "#dc2626", marginTop: 2 }}>
                {errors.name}
              </div>
            )}
          </div>

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
              Parent Category (Optional)
            </label>
            <select
              value={form.parent_id || ""}
              onChange={(e) =>
                handleFieldChange("parent_id", e.target.value ? parseInt(e.target.value) : null)
              }
              disabled={loading}
              style={{
                ...shellStyles.searchInput,
                fontSize: isMobile ? 11 : 12,
              }}
            >
              <option value="">-- No Parent --</option>
              {parentOptions.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
          </div>

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
              Description
            </label>
            <textarea
              value={form.description}
              onChange={(e) => handleFieldChange("description", e.target.value)}
              placeholder="Category description"
              disabled={loading}
              style={{
                ...shellStyles.searchInput,
                fontSize: isMobile ? 11 : 12,
                minHeight: 60,
                resize: "vertical",
              }}
            />
          </div>

          {errors._form && (
            <div
              style={{
                padding: "10px 12px",
                background: "#fee2e2",
                color: "#dc2626",
                fontSize: 12,
                borderRadius: 6,
                marginBottom: 12,
              }}
            >
              {errors._form}
            </div>
          )}
        </div>

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
            {loading ? "Saving..." : category?.id ? "Save Changes" : "Create Category"}
          </button>
        </div>
      </form>
    </Section>
  );
}
