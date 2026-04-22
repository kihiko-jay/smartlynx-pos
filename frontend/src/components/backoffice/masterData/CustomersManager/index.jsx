import { useState } from "react";
import CustomersList from "./CustomersList";
import CustomerForm from "./CustomerForm";
import CustomerDetailDrawer from "./CustomerDetailDrawer";
import { customersAPI } from "../../../../api/client";
import { Section } from "../../UIComponents";

export default function CustomersManager() {
  const [view, setView] = useState("list");
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [showDetailDrawer, setShowDetailDrawer] = useState(false);
  const [detailCustomer, setDetailCustomer] = useState(null);

  const handleView = (customer) => {
    setDetailCustomer(customer);
    setShowDetailDrawer(true);
  };

  const handleEdit = (customer) => {
    setSelectedCustomer(customer);
    setView("edit");
    setShowDetailDrawer(false);
  };

  const handleDelete = async (customerId) => {
    try {
      await customersAPI.update(customerId, { is_active: false });
      setRefreshTrigger(prev => prev + 1);
    } catch (e) {
      alert(`Failed to deactivate customer: ${e.message}`);
    }
  };

  const handleSave = () => {
    setView("list");
    setSelectedCustomer(null);
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
                setSelectedCustomer(null);
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
              ← Back to Customers
            </button>
          </div>
        </Section>
        <CustomerForm
          customer={selectedCustomer}
          onSave={handleSave}
          onCancel={() => {
            setView("list");
            setSelectedCustomer(null);
          }}
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
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Customers Master Data</h3>
          <button
            onClick={() => {
              setSelectedCustomer(null);
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
            + New Customer
          </button>
        </div>
      </Section>

      <CustomersList
        onEdit={handleEdit}
        onView={handleView}
        onDelete={handleDelete}
        refreshTrigger={refreshTrigger}
      />

      {showDetailDrawer && (
        <CustomerDetailDrawer
          customer={detailCustomer}
          onEdit={handleEdit}
          onClose={() => setShowDetailDrawer(false)}
        />
      )}
    </div>
  );
}
