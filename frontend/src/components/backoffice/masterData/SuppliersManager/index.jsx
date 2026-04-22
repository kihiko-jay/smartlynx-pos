import { useState, useEffect } from "react";
import SuppliersList from "./SuppliersList";
import SupplierForm from "./SupplierForm";
import { productsAPI } from "../../../../api/client";
import { Section } from "../../UIComponents";

export default function SuppliersManager() {
  const [view, setView] = useState("list");
  const [selectedSupplier, setSelectedSupplier] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleEdit = (supplier) => {
    setSelectedSupplier(supplier);
    setView("edit");
  };

  const handleDelete = async (supplierId) => {
    try {
      await productsAPI.update(supplierId, { is_active: false });
      setRefreshTrigger(prev => prev + 1);
    } catch (e) {
      alert(`Failed to delete supplier: ${e.message}`);
    }
  };

  const handleSave = () => {
    setView("list");
    setSelectedSupplier(null);
    setRefreshTrigger(prev => prev + 1);
  };

  if (view === "create" || view === "edit") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <Section>
          <div style={{ padding: "12px 16px" }}>
            <button
              onClick={() => {
                setView("list");
                setSelectedSupplier(null);
              }}
              style={{
                background: "none",
                border: "none",
                color: "#0d58d2",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
                textDecoration: "underline",
              }}
            >
              ← Back to Suppliers
            </button>
          </div>
        </Section>
        <SupplierForm
          supplier={selectedSupplier}
          onSave={handleSave}
          onCancel={() => setView("list")}
        />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
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
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Suppliers Master Data</h3>
          <button
            onClick={() => {
              setSelectedSupplier(null);
              setView("create");
            }}
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
            + New Supplier
          </button>
        </div>
      </Section>

      <SuppliersList
        onEdit={handleEdit}
        onDelete={handleDelete}
        refreshTrigger={refreshTrigger}
      />
    </div>
  );
}
