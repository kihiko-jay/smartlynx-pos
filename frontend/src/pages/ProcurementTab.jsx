/**
 * ProcurementTab — inbound inventory management with tab navigation
 *
 * Main Tabs:
 *   "pos"      — Purchase Orders (current & historical)
 *   "grns"     — Goods Received Notes (GRN)
 *   "invoices" — Invoice Matching
 *   "supplier-payments" — Supplier Payments
 *
 * Sub-screens:
 *   PO: "po-new", "po-view"
 *   GRN: "grn-new", "grn-view"
 */

import { useState } from "react";

// Import sub-components
import POList from "../components/procurement/POList";
import POForm from "../components/procurement/POForm";
import POView from "../components/procurement/POView";
import GRNList from "../components/procurement/GRNList";
import GRNForm from "../components/procurement/GRNForm";
import GRNView from "../components/procurement/GRNView";
import InvoiceMatching from "../components/procurement/InvoiceMatching";
import SupplierPaymentList from "../components/procurement/SupplierPaymentList";
import SupplierPaymentForm from "../components/procurement/SupplierPaymentForm";

export default function ProcurementTab() {
  const [screen, setScreen] = useState("pos");
  const [poId, setPoId] = useState(null);
  const [grnId, setGrnId] = useState(null);
  const [prefillPoId, setPrefillPoId] = useState(null);

  // Determine current main tab
  const mainTab = 
    screen === "grns" || screen === "grn-new" || screen === "grn-view" ? "grns" :
    screen === "invoices" ? "invoices" :
    screen === "supplier-payments" || screen === "supplier-payment-new" ? "supplier-payments" :
    "pos";

  const goToPOList = () => {
    setScreen("pos");
    setPoId(null);
  };

  const goToPOForm = (id = null) => {
    setPoId(id);
    setScreen("po-new");
  };

  const goToPOView = (id) => {
    setPoId(id);
    setScreen("po-view");
  };

  const goToGRNList = () => {
    setScreen("grns");
    setGrnId(null);
    setPrefillPoId(null);
  };

  const goToGRNForm = (poId = null) => {
    setPrefillPoId(poId);
    setGrnId(null);
    setScreen("grn-new");
  };

  const goToGRNView = (id) => {
    setGrnId(id);
    setScreen("grn-view");
  };

  const goToInvoiceMatching = () => {
    setScreen("invoices");
  };

  const goToSupplierPayments = () => {
    setScreen("supplier-payments");
  };

  const renderScreen = () => {
    switch (screen) {
      case "pos":
        return (
          <POList
            onNew={() => goToPOForm()}
            onView={goToPOView}
            onEdit={goToPOForm}
          />
        );

      case "po-new":
        return (
          <POForm
            poId={poId}
            onBack={goToPOList}
            onSaved={goToPOView}
          />
        );

      case "po-view":
        return (
          <POView
            poId={poId}
            onBack={goToPOList}
            onCreateGRN={goToGRNForm}
          />
        );

      case "grns":
        return (
          <GRNList
            onNew={() => goToGRNForm()}
            onView={goToGRNView}
          />
        );

      case "grn-new":
        return (
          <GRNForm
            prefillPoId={prefillPoId}
            onBack={goToGRNList}
            onSaved={goToGRNView}
          />
        );

      case "grn-view":
        return (
          <GRNView
            grnId={grnId}
            onBack={goToGRNList}
          />
        );

      case "invoices":
        return <InvoiceMatching />;
      case "supplier-payments":
        return <SupplierPaymentList onNew={() => setScreen("supplier-payment-new")} />;
      case "supplier-payment-new":
        return <SupplierPaymentForm onBack={() => setScreen("supplier-payments")} onSaved={() => setScreen("supplier-payments")} />;

      default:
        return null;
    }
  };

  const tabStyle = {
    display: "flex",
    gap: "8px",
    borderBottom: "2px solid #e0e0e0",
    marginBottom: "24px",
    paddingBottom: "0",
  };

  const tabButtonStyle = (isActive) => ({
    padding: "12px 16px",
    border: "none",
    background: "transparent",
    cursor: "pointer",
    fontSize: "14px",
    fontWeight: isActive ? "600" : "500",
    color: isActive ? "#1a1a1a" : "#666",
    borderBottom: isActive ? "3px solid #2563eb" : "none",
    marginBottom: "-2px",
    transition: "all 0.2s",
  });

  return (
    <div style={{ padding: "20px 24px" }}>
      {/* Tab Navigation */}
      <div style={tabStyle}>
        <button
          style={tabButtonStyle(mainTab === "pos")}
          onClick={goToPOList}
        >
          📋 Purchase Orders
        </button>
        <button
          style={tabButtonStyle(mainTab === "grns")}
          onClick={goToGRNList}
        >
          📦 Goods Received (GRN)
        </button>
        <button
          style={tabButtonStyle(mainTab === "invoices")}
          onClick={goToInvoiceMatching}
        >
          🔗 Invoice Matching
        </button>
        <button
          style={tabButtonStyle(mainTab === "supplier-payments")}
          onClick={goToSupplierPayments}
        >
          💳 Supplier Payments
        </button>
      </div>

      {/* Content Area */}
      {renderScreen()}
    </div>
  );
}