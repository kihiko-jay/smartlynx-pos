import { useState, useEffect } from "react";
import CategoriesList from "./CategoriesList";
import CategoryForm from "./CategoryForm";
import { productsAPI } from "../../../../api/client";
import { Section } from "../../UIComponents";

export default function CategoriesManager() {
  const [view, setView] = useState("list");
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [categories, setCategories] = useState([]);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    loadCategories();
  }, [refreshTrigger]);

  const loadCategories = async () => {
    try {
      const result = await productsAPI.categories();
      // Store all categories for parent selection
      setCategories(result?.items || result || []);
    } catch (e) {
      console.warn("Failed to load categories:", e);
    }
  };

  const handleEdit = (category) => {
    setSelectedCategory(category);
    setView("edit");
  };

  const handleCreate = () => {
    setSelectedCategory(null);
    setView("create");
  };

  const handleDelete = async (categoryId) => {
    try {
      // Soft delete via deactivate
      await productsAPI.update(categoryId, { is_active: false });
      setRefreshTrigger(prev => prev + 1);
    } catch (e) {
      alert(`Failed to delete category: ${e.message}`);
    }
  };

  const handleSave = () => {
    setView("list");
    setSelectedCategory(null);
    setRefreshTrigger(prev => prev + 1);
  };

  const handleCancel = () => {
    setView("list");
    setSelectedCategory(null);
  };

  if (view === "create" || view === "edit") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <Section>
          <div style={{ padding: "12px 16px" }}>
            <button
              onClick={handleCancel}
              style={{
                background: "none",
                border: "none",
                color: "#0d58d2",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
                textDecoration: "underline",
                marginBottom: 8,
              }}
            >
              ← Back to Categories
            </button>
          </div>
        </Section>

        <CategoryForm
          category={selectedCategory}
          categories={categories}
          onSave={handleSave}
          onCancel={handleCancel}
        />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Toolbar */}
      <Section>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "12px 16px",
            gap: 8,
          }}
        >
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Product Categories</h3>
          <button
            onClick={handleCreate}
            style={{
              background: "linear-gradient(180deg, #1b6cff 0%, #0d4fd6 100%)",
              border: "1px solid #2f65d9",
              borderRadius: 8,
              color: "#fff",
              cursor: "pointer",
              fontFamily: "inherit",
              fontSize: 12,
              fontWeight: 700,
              padding: "8px 12px",
              whiteSpace: "nowrap",
            }}
          >
            + New Category
          </button>
        </div>
      </Section>

      {/* Categories List */}
      <CategoriesList
        onEdit={handleEdit}
        onDelete={handleDelete}
        refreshTrigger={refreshTrigger}
      />
    </div>
  );
}
