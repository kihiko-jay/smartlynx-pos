import { useState, useEffect } from "react";
import { customersAPI, fmtKES } from "../../../../api/client";
import { shellStyles } from "../../styles";
import { Section, EmptyState } from "../../UIComponents";

export default function CustomerDetailDrawer({ customer, onEdit, onClose }) {
  const [creditSummary, setCreditSummary] = useState(null);
  const [txnHistory, setTxnHistory] = useState(null);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (customer?.id) {
      loadDetails();
    }
  }, [customer?.id]);

  const loadDetails = async () => {
    try {
      const [credit, txns] = await Promise.all([
        customersAPI.creditSummary(customer.id).catch(() => null),
        customersAPI.transactionHistory(customer.id).catch(() => null),
      ]);
      setCreditSummary(credit);
      setTxnHistory(txns);
    } catch (e) {
      console.warn("Failed to load customer details:", e);
    }
  };

  if (!customer) return null;

  return (
    <div
      style={{
        position: "fixed",
        right: 0,
        top: 0,
        width: isMobile ? "100%" : "400px",
        height: "100vh",
        background: "#fff",
        boxShadow: "-2px 0 8px rgba(0,0,0,0.15)",
        zIndex: 1000,
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          ...shellStyles.panelTitle(isMobile),
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "10px 12px",
        }}
      >
        <span>{customer.name}</span>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "#fff",
            fontSize: 20,
            cursor: "pointer",
            padding: "4px 8px",
          }}
        >
          ✕
        </button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "12px" }}>
        <Section title="Customer Info">
          <div style={{ display: "grid", gap: 12, padding: "12px" }}>
            <div>
              <div style={{ fontSize: 10, color: "#64748b", fontWeight: 700, marginBottom: 2 }}>
                PHONE
              </div>
              <div style={{ fontSize: 12 }}>{customer.phone || "-"}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: "#64748b", fontWeight: 700, marginBottom: 2 }}>
                EMAIL
              </div>
              <div style={{ fontSize: 12 }}>{customer.email || "-"}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: "#64748b", fontWeight: 700, marginBottom: 2 }}>
                LOYALTY POINTS
              </div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>{customer.loyalty_points}</div>
            </div>
          </div>
        </Section>

        {creditSummary && (
          <Section title="Credit Summary" style={{ marginTop: 12 }}>
            <div style={{ display: "grid", gap: 12, padding: "12px", fontSize: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#64748b" }}>Credit Limit:</span>
                <span style={{ fontWeight: 700 }}>{fmtKES(creditSummary.credit_limit)}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", color: creditSummary.credit_balance > 0 ? "#dc2626" : "#064e3b" }}>
                <span style={{ color: "#64748b" }}>Credit Balance:</span>
                <span style={{ fontWeight: 700 }}>{fmtKES(creditSummary.credit_balance)}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", color: "#0d58d2" }}>
                <span style={{ color: "#64748b" }}>Available:</span>
                <span style={{ fontWeight: 700 }}>{fmtKES(creditSummary.available_credit)}</span>
              </div>
              {creditSummary.credit_limit > 0 && (
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "#64748b" }}>Utilization:</span>
                  <span style={{ fontWeight: 700 }}>
                    {creditSummary.credit_utilization_percent.toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          </Section>
        )}

        {txnHistory && (
          <Section title="Transaction History" style={{ marginTop: 12 }}>
            <div style={{ display: "grid", gap: 8, padding: "12px", fontSize: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#64748b" }}>Total Transactions:</span>
                <span style={{ fontWeight: 700 }}>{txnHistory.total_transactions}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", color: "#047857" }}>
                <span style={{ color: "#64748b" }}>Total Amount:</span>
                <span style={{ fontWeight: 700 }}>{fmtKES(txnHistory.total_amount)}</span>
              </div>
              {txnHistory.last_transaction_date && (
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "#64748b" }}>Last Transaction:</span>
                  <span style={{ fontWeight: 600 }}>
                    {new Date(txnHistory.last_transaction_date).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          </Section>
        )}

        {customer.notes && (
          <Section title="Notes" style={{ marginTop: 12 }}>
            <div style={{ padding: "12px", fontSize: 12 }}>
              {customer.notes}
            </div>
          </Section>
        )}
      </div>

      <div
        style={{
          display: "flex",
          gap: 8,
          padding: "10px 12px",
          borderTop: "1px solid #cbd5e1",
          background: "#f9fafb",
        }}
      >
        <button
          onClick={() => {
            onEdit(customer);
            onClose();
          }}
          style={shellStyles.primaryButton(isMobile)}
        >
          Edit
        </button>
        <button
          onClick={onClose}
          style={{ ...shellStyles.smallButton(isMobile), background: "#6b7280", flex: 1 }}
        >
          Close
        </button>
      </div>
    </div>
  );
}
