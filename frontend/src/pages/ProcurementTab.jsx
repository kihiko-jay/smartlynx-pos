/**
 * ProcurementTab — inbound inventory management
 *
 * Sub-screens:
 *   "pos"      — Purchase Orders list
 *   "po-new"   — Create / Edit PO
 *   "po-view"  — PO detail + status actions
 *   "grns"     — GRN list
 *   "grn-new"  — Receive Inventory (create GRN)
 *   "grn-view" — GRN detail (print-friendly)
 *   "invoices" — Invoice Matching
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

  return (
    <div style={{ padding: "20px 24px" }}>
      {renderScreen()}
    </div>
  );
}