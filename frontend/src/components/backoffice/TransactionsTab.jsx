import { useEffect, useMemo, useState } from "react";
import { fmtKES, getSession, returnsAPI, transactionsAPI } from "../../api/client";
import { shellStyles } from "./styles";
import { EmptyState, Section, TableShell } from "./UIComponents";

const RETURN_REASONS = [
  ["change_of_mind", "Change of mind"],
  ["defective", "Defective"],
  ["wrong_item", "Wrong item"],
  ["damaged_in_transit", "Damaged in transit"],
  ["expired", "Expired"],
  ["quality_issue", "Quality issue"],
  ["other", "Other"],
];

const REFUND_METHODS = [
  ["cash", "Cash"],
  ["mpesa", "M-Pesa"],
  ["card", "Card"],
  ["credit_note", "Credit note"],
  ["store_credit", "Store credit"],
];

const inputStyle = {
  width: "100%",
  border: "1px solid #92a8c9",
  background: "#fff",
  borderRadius: 6,
  padding: "8px 10px",
  fontSize: 13,
  outline: "none",
};

export default function TransactionsTab() {
  const [txns, setTxns] = useState([]);
  const [returns, setReturns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [returnsLoading, setReturnsLoading] = useState(true);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [selectedTxn, setSelectedTxn] = useState(null);
  const [returnReason, setReturnReason] = useState("defective");
  const [reasonNotes, setReasonNotes] = useState("");
  const [approveMethod, setApproveMethod] = useState("cash");
  const [approveRef, setApproveRef] = useState("");
  const [rejectNotes, setRejectNotes] = useState("");
  const [selectedItems, setSelectedItems] = useState({});
  const session = getSession();
  const canApprove = ["supervisor", "manager", "admin"].includes(session?.role);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const loadTransactions = async () => {
    setLoading(true);
    try {
      const data = await transactionsAPI.list({ limit: 50 });
      setTxns(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || "Failed to load transactions");
    } finally {
      setLoading(false);
    }
  };

  const loadReturns = async () => {
    setReturnsLoading(true);
    try {
      const data = await returnsAPI.list({ limit: 50 });
      setReturns(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || "Failed to load returns");
    } finally {
      setReturnsLoading(false);
    }
  };

  useEffect(() => {
    loadTransactions();
    loadReturns();
  }, []);

  const openReturnBuilder = async (txnId) => {
    setBusyId(txnId);
    setError("");
    setMessage("");
    try {
      const detail = await transactionsAPI.getById(txnId);
      setSelectedTxn(detail);
      const next = {};
      (detail?.items || []).forEach((item) => {
        next[item.id] = { checked: false, qty: 1, is_restorable: true, damaged_notes: "" };
      });
      setSelectedItems(next);
      setReasonNotes("");
    } catch (err) {
      setError(err.message || "Failed to load transaction details");
    } finally {
      setBusyId(null);
    }
  };

  const closeReturnBuilder = () => {
    setSelectedTxn(null);
    setSelectedItems({});
    setApproveRef("");
    setRejectNotes("");
  };

  const selectedCount = useMemo(
    () => Object.values(selectedItems).filter((item) => item.checked).length,
    [selectedItems]
  );

  const submitReturnRequest = async () => {
    const items = (selectedTxn?.items || [])
      .filter((item) => selectedItems[item.id]?.checked)
      .map((item) => ({
        original_txn_item_id: item.id,
        qty_returned: Number(selectedItems[item.id]?.qty || 0),
        is_restorable: !!selectedItems[item.id]?.is_restorable,
        damaged_notes: selectedItems[item.id]?.damaged_notes || null,
      }))
      .filter((item) => item.qty_returned > 0);

    if (!items.length) {
      setError("Select at least one line item to return.");
      return;
    }

    setBusyId(`create-${selectedTxn.id}`);
    setError("");
    setMessage("");
    try {
      const created = await returnsAPI.create({
        original_txn_id: selectedTxn.id,
        return_reason: returnReason,
        reason_notes: reasonNotes || null,
        items,
      });
      setMessage(`Return ${created.return_number} created and awaiting approval.`);
      await loadReturns();
      closeReturnBuilder();
    } catch (err) {
      setError(err.message || "Failed to create return request");
    } finally {
      setBusyId(null);
    }
  };

  const approveReturn = async (returnId) => {
    setBusyId(`approve-${returnId}`);
    setError("");
    setMessage("");
    try {
      await returnsAPI.approve(returnId, {
        refund_method: approveMethod,
        refund_ref: approveRef || null,
        notes: null,
      });
      setMessage("Return approved and completed.");
      setApproveRef("");
      await loadReturns();
      await loadTransactions();
    } catch (err) {
      setError(err.message || "Failed to approve return");
    } finally {
      setBusyId(null);
    }
  };

  const rejectReturn = async (returnId) => {
    if (!rejectNotes || rejectNotes.trim().length < 3) {
      setError("Add a short rejection note before rejecting.");
      return;
    }
    setBusyId(`reject-${returnId}`);
    setError("");
    setMessage("");
    try {
      await returnsAPI.reject(returnId, { rejection_notes: rejectNotes.trim() });
      setMessage("Return rejected.");
      setRejectNotes("");
      await loadReturns();
    } catch (err) {
      setError(err.message || "Failed to reject return");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Section title="Transaction Journal">
        {message ? <div style={{ marginBottom: 12, color: "#166534", fontWeight: 700 }}>{message}</div> : null}
        {error ? <div style={{ marginBottom: 12, color: "#b42318", fontWeight: 700 }}>{error}</div> : null}
        {loading ? (
          <EmptyState text="Loading transactions..." />
        ) : (
          <TableShell
            headers={["TXN Number", "Total", "Payment", "Status", "Cloud Sync", "Date", "Actions"]}
            hideColumns={isMobile ? [4, 5] : []}
          >
            {(txns || []).map((t, idx) => {
              const displayCols = isMobile
                ? ["TXN Number", "Total", "Payment", "Status", "Actions"]
                : ["TXN Number", "Total", "Payment", "Status", "Cloud Sync", "Date", "Actions"];
              return (
                <div
                  key={t.id || idx}
                  style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${displayCols.length}, minmax(0,1fr))`,
                    borderTop: idx ? "1px solid #e2e8f0" : "none",
                    background: idx % 2 ? "#f8fbff" : "#fff",
                  }}
                >
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontWeight: 700, color: "#155eef", fontSize: isMobile ? 11 : 12 }}>{t.txn_number}</div>
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: isMobile ? 11 : 12 }}>{fmtKES(t.total)}</div>
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", textTransform: "uppercase", fontSize: isMobile ? 10 : 12 }}>{t.payment_method}</div>
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: isMobile ? 11 : 12 }}>{t.status}</div>
                  {!isMobile && <div style={{ padding: "10px 12px", fontSize: 12 }}>{t.sync_status || "pending"}</div>}
                  {!isMobile && <div style={{ padding: "10px 12px", color: "#64748b", fontSize: 12 }}>{new Date(t.created_at).toLocaleString("en-KE", { dateStyle: "short", timeStyle: "short" })}</div>}
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px" }}>
                    <button onClick={() => openReturnBuilder(t.id)} style={shellStyles.smallButton(isMobile)} disabled={busyId === t.id}>
                      {busyId === t.id ? "Loading..." : "Return / Refund"}
                    </button>
                  </div>
                </div>
              );
            })}
          </TableShell>
        )}
      </Section>

      {selectedTxn ? (
        <Section
          title={`Create Return — ${selectedTxn.txn_number}`}
          right={<button onClick={closeReturnBuilder} style={shellStyles.smallButton(isMobile)}>Close</button>}
        >
          <div style={{ display: "grid", gap: 12, padding: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>Return reason</div>
                <select value={returnReason} onChange={(e) => setReturnReason(e.target.value)} style={inputStyle}>
                  {RETURN_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>Reason notes</div>
                <input value={reasonNotes} onChange={(e) => setReasonNotes(e.target.value)} style={inputStyle} placeholder="Optional notes for supervisor" />
              </div>
            </div>

            <div style={{ border: "1px solid #cbd5e1", borderRadius: 8, overflow: "hidden" }}>
              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1.4fr .7fr .7fr" : "1.6fr .7fr .7fr .8fr .9fr", background: "#edf4ff", fontWeight: 700, fontSize: 12 }}>
                <div style={{ padding: "10px 12px" }}>Item</div>
                <div style={{ padding: "10px 12px" }}>Sold Qty</div>
                <div style={{ padding: "10px 12px" }}>Return Qty</div>
                {!isMobile && <div style={{ padding: "10px 12px" }}>Restock</div>}
                {!isMobile && <div style={{ padding: "10px 12px" }}>Line Total</div>}
              </div>
              {(selectedTxn.items || []).map((item, idx) => (
                <div key={item.id} style={{ display: "grid", gridTemplateColumns: isMobile ? "1.4fr .7fr .7fr" : "1.6fr .7fr .7fr .8fr .9fr", borderTop: idx ? "1px solid #e2e8f0" : "none", background: idx % 2 ? "#f8fbff" : "#fff" }}>
                  <div style={{ padding: "10px 12px" }}>
                    <label style={{ display: "flex", gap: 8, alignItems: "start" }}>
                      <input type="checkbox" checked={!!selectedItems[item.id]?.checked} onChange={(e) => setSelectedItems((prev) => ({ ...prev, [item.id]: { ...prev[item.id], checked: e.target.checked } }))} />
                      <span>
                        <strong>{item.product_name}</strong><br />
                        <span style={{ color: "#64748b", fontSize: 12 }}>{item.sku}</span>
                      </span>
                    </label>
                  </div>
                  <div style={{ padding: "10px 12px" }}>{item.qty}</div>
                  <div style={{ padding: "10px 12px" }}>
                    <input
                      type="number"
                      min="1"
                      max={item.qty}
                      value={selectedItems[item.id]?.qty || 1}
                      onChange={(e) => setSelectedItems((prev) => ({ ...prev, [item.id]: { ...prev[item.id], qty: Math.max(1, Math.min(item.qty, Number(e.target.value || 1))) } }))}
                      style={{ ...inputStyle, padding: "6px 8px" }}
                    />
                  </div>
                  {!isMobile && <div style={{ padding: "10px 12px" }}><input type="checkbox" checked={!!selectedItems[item.id]?.is_restorable} onChange={(e) => setSelectedItems((prev) => ({ ...prev, [item.id]: { ...prev[item.id], is_restorable: e.target.checked } }))} /></div>}
                  {!isMobile && <div style={{ padding: "10px 12px" }}>{fmtKES(item.line_total)}</div>}
                </div>
              ))}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <div style={{ color: "#475467", fontSize: 13 }}>Selected lines: {selectedCount}</div>
              <button onClick={submitReturnRequest} style={shellStyles.primaryButton(isMobile)} disabled={busyId === `create-${selectedTxn.id}`}>
                {busyId === `create-${selectedTxn.id}` ? "Creating..." : "Create Return Request"}
              </button>
            </div>
          </div>
        </Section>
      ) : null}

      <Section title="Returns / Refunds Queue">
        {returnsLoading ? (
          <EmptyState text="Loading returns..." />
        ) : !(returns || []).length ? (
          <EmptyState text="No returns created yet." />
        ) : (
          <div style={{ display: "grid", gap: 12, padding: 12 }}>
            {(returns || []).map((ret) => (
              <div key={ret.id} style={{ border: "1px solid #cbd5e1", borderRadius: 8, background: "#fff", padding: 12, display: "grid", gap: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                  <div>
                    <div style={{ fontWeight: 800 }}>{ret.return_number}</div>
                    <div style={{ color: "#475467", fontSize: 12 }}>Original: {ret.original_txn_number}</div>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ padding: "4px 8px", borderRadius: 999, background: ret.status === "completed" ? "#dcfce7" : ret.status === "rejected" ? "#fee2e2" : "#fef3c7", color: "#111827", fontSize: 12, fontWeight: 700 }}>{ret.status}</span>
                    <span style={{ fontSize: 12, color: "#475467" }}>{ret.return_reason}</span>
                    {ret.refund_amount != null ? <span style={{ fontSize: 12, fontWeight: 700 }}>{fmtKES(ret.refund_amount)}</span> : null}
                  </div>
                </div>

                {ret.status === "pending" && canApprove ? (
                  <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr 1fr auto auto", gap: 8, alignItems: "end" }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>Refund method</div>
                      <select value={approveMethod} onChange={(e) => setApproveMethod(e.target.value)} style={inputStyle}>
                        {REFUND_METHODS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>Refund ref</div>
                      <input value={approveRef} onChange={(e) => setApproveRef(e.target.value)} style={inputStyle} placeholder="M-Pesa ref / auth code" />
                    </div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>Reject note</div>
                      <input value={rejectNotes} onChange={(e) => setRejectNotes(e.target.value)} style={inputStyle} placeholder="Why rejected?" />
                    </div>
                    <button onClick={() => approveReturn(ret.id)} style={shellStyles.primaryButton(isMobile)} disabled={busyId === `approve-${ret.id}`}>{busyId === `approve-${ret.id}` ? "Approving..." : "Approve"}</button>
                    <button onClick={() => rejectReturn(ret.id)} style={shellStyles.smallButton(isMobile)} disabled={busyId === `reject-${ret.id}`}>{busyId === `reject-${ret.id}` ? "Rejecting..." : "Reject"}</button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
