import { useState, useEffect } from "react";
import ProductsList from "./ProductsList";
import ProductForm from "./ProductForm";
import ProductDetailDrawer from "./ProductDetailDrawer";
import { productsAPI } from "../../../../api/client";
import { Section } from "../../UIComponents";

export default function ProductsManager() {
  const [view, setView] = useState("list"); // list, create, edit
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [categories, setCategories] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [showDetailDrawer, setShowDetailDrawer] = useState(false);
  const [detailProduct, setDetailProduct] = useState(null);

  useEffect(() => {
    loadFilterData();
  }, []);

  const loadFilterData = async () => {
    try {
      const [cats, sups] = await Promise.all([
        productsAPI.categories().then(r => r?.items || r || []),
        productsAPI.suppliers().then(r => r?.items || r || []),
      ]);
      setCategories(cats);
      setSuppliers(sups);
    } catch (e) {
      console.warn("Failed to load categories/suppliers:", e);
    }
  };

  const handleView = (product) => {
    setDetailProduct(product);
    setShowDetailDrawer(true);
  };

  const handleEdit = (product) => {
    setSelectedProduct(product);
    setView("edit");
    setShowDetailDrawer(false);
  };

  const handleCreate = () => {
    setSelectedProduct(null);
    setView("create");
  };

  const handleDelete = async (productId) => {
    try {
      // The backend uses soft delete via deactivate
      await productsAPI.update(productId, { is_active: false });
      setRefreshTrigger(prev => prev + 1);
    } catch (e) {
      alert(`Failed to delete product: ${e.message}`);
    }
  };

  const handleSave = () => {
    setView("list");
    setSelectedProduct(null);
    setRefreshTrigger(prev => prev + 1);
    loadFilterData();
  };

  const handleCancel = () => {
    setView("list");
    setSelectedProduct(null);
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
              ← Back to Products
            </button>
          </div>
        </Section>

        <ProductForm
          product={selectedProduct}
          categories={categories}
          suppliers={suppliers}
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
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Products Master Data</h3>
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
            + New Product
          </button>
        </div>
      </Section>

      {/* Products List */}
      <ProductsList
        onEdit={handleEdit}
        onView={handleView}
        onDelete={handleDelete}
        onRefresh={loadFilterData}
        refreshTrigger={refreshTrigger}
      />

      {/* Detail Drawer */}
      {showDetailDrawer && (
        <ProductDetailDrawer
          product={detailProduct}
          onEdit={handleEdit}
          onClose={() => setShowDetailDrawer(false)}
        />
      )}
    </div>
  );
}
