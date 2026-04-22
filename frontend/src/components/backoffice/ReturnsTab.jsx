/**
 * ReturnsTab — Returns & Refunds management module
 *
 * Panels:
 *   List     — All returns for the store with status/filter controls
 *   Initiate — Look up a completed transaction and create a return request
 *   Approve  — Supervisor approval modal (refund method + confirm/reject)
 *   Detail   — Full return detail drawer
 *
 * Role rules (mirrors backend):
 *   CASHIER    — can create returns and view list
 *   SUPERVISOR — can additionally approve/reject
 *   MANAGER / ADMIN — full access
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { returnsAPI, transactionsAPI, fmtKES, getSession } from "../../api/client";
import { Section, EmptyState } from "./UIComponents";
import { shellStyles } from "./styles";

// ── Constants ─────────────────────────────────────────────────────────────────

const STATUS_COLORS = {
  pending:   { bg: "#fef3c7", text: "#b45309", border: "#fde68a" },
  completed: { bg: "#dcfce7", text: "#15803d", border: "#86efac" },
  rejected:  { bg: "#fee2e2", text: "#dc2626", border: "#fca5a5" },
};

const REASON_LABELS = {
  change_of_mind:     "Change of Mind",
  defective:          "Defective Item",
  wrong_item:         "Wrong Item",
  damaged_in_transit: "Damaged in Transit",
  expired:            "Expired",
  quality_issue:      "Quality Issue",
  other:              "Other",
};

const REFUND_METHODS = [
  { value: "cash",         label: "Cash" },
  { value: "mpesa",        label: "M-PESA" },
  { value: "card",         label: "Card" },
  { value: "store_credit", label: "Store Credit" },
  { value: "credit_note",  label: "Credit Note" },
];

const RETURN_REASONS = Object.entries(REASON_LABELS).map(([value, label]) => ({ value, label }));

// ── Helpers ───────────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const c = STATUS_COLORS[status] || STATUS_COLORS.pending;
  return (
    <span style={{
      background: c.bg, color: c.text, border: `1px solid ${c.border}`,
      borderRadius: 20, padding: "2px 10px", fontSize: 11, fontWeight: 700,
      textTransform: "uppercase", letterSpacing: "0.04em",
    }}>
      {status}
    </span>
  );
}

function fmt(v) { return fmtKES(v ?? 0); }

function useMobile() {
  const [m, setM] = useState(typeof window !== "undefined" && window.innerWidth < 768);
  useEffect(() => {
    const h = () => setM(window.innerWidth < 768);
    window.addEventListener("resize", h);
    return () => window.removeEventListener("resize", h);
  }, []);
  return m;
}

function canApprove(role) {
  return ["supervisor", "manager", "admin", "platform_owner"].includes(role?.toLowerCase());
}

// ── Return List ───────────────────────────────────────────────────────────────

function ReturnsList({ onSelect, onCreateNew, refreshKey }) {
  const isMobile = useMobile();
  const [returns, setReturns]   = useState([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);
  const [statusFilter, setStatusFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const data = await returnsAPI.list(statusFilter ? { status: statusFilter } : {});
      setReturns(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, refreshKey]);

  useEffect(() => { load(); }, [load]);

  const session = getSession();

  return (
    <Section
      title="Returns & Refunds"
      right={
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {/* Status filter pills */}
          {["", "pending", "completed", "rejected"].map((s) => (
            <button
              key={s || "all"}
              onClick={() => setStatusFilter(s)}
              style={{
                padding: "4px 12px", borderRadius: 20, border: "1px solid",
                fontSize: 11, fontWeight: 700, cursor: "pointer",
                background: statusFilter === s ? "#1b6cff" : "#f8fafc",
                color: statusFilter === s ? "#fff" : "#475569",
                borderColor: statusFilter === s ? "#1b6cff" : "#cbd5e1",
              }}
            >
              {s ? s.charAt(0).toUpperCase() + s.slice(1) : "All"}
            </button>
          ))}
          <button
            onClick={onCreateNew}
            style={{ ...shellStyles.smallButton(isMobile), background: "#1b6cff", color: "#fff", borderColor: "#1b6cff" }}
          >
            + New Return
          </button>
        </div>
      }
    >
      {loading && <EmptyState text="Loading returns..." />}
      {error   && <EmptyState text={`Error: ${error}`} />}
      {!loading && !error && returns.length === 0 && (
        <EmptyState text="No returns found. Click '+ New Return' to initiate a refund." />
      )}
      {!loading && !error && returns.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: isMobile ? 11 : 13 }}>
            <thead>
              <tr style={{ background: "#edf4ff", borderBottom: "2px solid #bfdbfe" }}>
                {["Return #", "Original TXN", "Reason", "Status", "Refund Method", "Amount", "Date", ""].map((h) => (
                  <th key={h} style={{
                    padding: isMobile ? "6px 8px" : "9px 12px", textAlign: "left",
                    fontWeight: 700, fontSize: 11, textTransform: "uppercase", color: "#334155",
                    whiteSpace: "nowrap",
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {returns.map((r, i) => (
                <tr
                  key={r.id}
                  style={{ background: i % 2 === 0 ? "#fff" : "#f8fafc", borderBottom: "1px solid #e2e8f0", cursor: "pointer" }}
                  onClick={() => onSelect(r)}
                >
                  <td style={{ padding: isMobile ? "6px 8px" : "8px 12px", fontFamily: "monospace", fontWeight: 700, color: "#1b6cff" }}>
                    {r.return_number}
                  </td>
                  <td style={{ padding: isMobile ? "6px 8px" : "8px 12px", fontFamily: "monospace", fontSize: 12 }}>
                    {r.original_txn_number}
                  </td>
                  <td style={{ padding: isMobile ? "6px 8px" : "8px 12px" }}>
                    {REASON_LABELS[r.return_reason] || r.return_reason}
                    {r.is_partial && (
                      <span style={{ marginLeft: 6, fontSize: 10, color: "#94a3b8", fontWeight: 600 }}>PARTIAL</span>
                    )}
                  </td>
                  <td style={{ padding: isMobile ? "6px 8px" : "8px 12px" }}>
                    <StatusBadge status={r.status} />
                  </td>
                  <td style={{ padding: isMobile ? "6px 8px" : "8px 12px", color: "#64748b" }}>
                    {r.refund_method ? r.refund_method.replace("_", " ").toUpperCase() : "—"}
                  </td>
                  <td style={{ padding: isMobile ? "6px 8px" : "8px 12px", fontFamily: "monospace", fontWeight: 600 }}>
                    {r.refund_amount ? fmt(r.refund_amount) : "—"}
                  </td>
                  <td style={{ padding: isMobile ? "6px 8px" : "8px 12px", color: "#64748b", fontSize: 12 }}>
                    {new Date(r.created_at).toLocaleDateString("en-KE")}
                  </td>
                  <td style={{ padding: isMobile ? "6px 8px" : "8px 12px" }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); onSelect(r); }}
                      style={{ ...shellStyles.smallButton(isMobile), padding: "2px 10px", minHeight: 26, fontSize: 11 }}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

// ── Return Detail Drawer ──────────────────────────────────────────────────────

function ReturnDetail({ returnId, onClose, onApproveReject, refreshKey }) {
  const isMobile = useMobile();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const session = getSession();

  useEffect(() => {
    if (!returnId) return;
    setLoading(true); setError(null);
    returnsAPI.getById(returnId)
      .then(setDetail)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [returnId, refreshKey]);

  if (loading) return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#fff", borderRadius: 12, padding: 32 }}><EmptyState text="Loading..." /></div>
    </div>
  );

  if (error || !detail) return null;

  const r = detail;
  const isActionable = r.status === "pending" && canApprove(session?.role);

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 1000, display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
      <div style={{
        background: "#fff", borderRadius: "16px 16px 0 0", width: "100%", maxWidth: 760,
        maxHeight: "90vh", overflowY: "auto", padding: isMobile ? 16 : 28, boxShadow: "0 -8px 32px rgba(0,0,0,0.18)",
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: isMobile ? 15 : 18, color: "#1e293b" }}>{r.return_number}</div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
              Original: <span style={{ fontFamily: "monospace", fontWeight: 600 }}>{r.original_txn_number}</span>
              &nbsp;·&nbsp;<StatusBadge status={r.status} />
            </div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 22, cursor: "pointer", color: "#94a3b8", lineHeight: 1 }}>×</button>
        </div>

        {/* Meta grid */}
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(4,1fr)", gap: 12, marginBottom: 20 }}>
          {[
            { label: "Reason",        value: REASON_LABELS[r.return_reason] || r.return_reason },
            { label: "Refund Method", value: r.refund_method ? r.refund_method.replace("_"," ").toUpperCase() : "Pending" },
            { label: "Refund Amount", value: r.refund_amount ? fmt(r.refund_amount) : "—" },
            { label: "Date",          value: new Date(r.created_at).toLocaleDateString("en-KE") },
          ].map(({ label, value }) => (
            <div key={label} style={{ background: "#f8fafc", borderRadius: 8, padding: "10px 14px" }}>
              <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>{value}</div>
            </div>
          ))}
        </div>

        {/* Notes */}
        {r.reason_notes && (
          <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "10px 14px", marginBottom: 16, fontSize: 13, color: "#92400e" }}>
            <strong>Notes:</strong> {r.reason_notes}
          </div>
        )}
        {r.rejection_notes && (
          <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "10px 14px", marginBottom: 16, fontSize: 13, color: "#991b1b" }}>
            <strong>Rejection reason:</strong> {r.rejection_notes}
          </div>
        )}

        {/* Items */}
        <div style={{ fontWeight: 700, fontSize: 13, color: "#334155", marginBottom: 8 }}>Returned Items</div>
        <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden", marginBottom: 20 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: isMobile ? 11 : 13 }}>
            <thead>
              <tr style={{ background: "#f8fafc" }}>
                {["SKU", "Product", "Qty", "Unit Price", "Line Total", "Restorable?"].map((h) => (
                  <th key={h} style={{ padding: "8px 12px", textAlign: ["Qty","Unit Price","Line Total"].includes(h) ? "right" : "left", fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(r.items || []).map((item, i) => (
                <tr key={item.id} style={{ borderTop: "1px solid #f1f5f9", background: i % 2 === 0 ? "#fff" : "#fafafa" }}>
                  <td style={{ padding: "7px 12px", fontFamily: "monospace", fontSize: 12 }}>{item.sku}</td>
                  <td style={{ padding: "7px 12px" }}>{item.product_name}</td>
                  <td style={{ padding: "7px 12px", textAlign: "right" }}>{item.qty_returned}</td>
                  <td style={{ padding: "7px 12px", textAlign: "right", fontFamily: "monospace" }}>{fmt(item.unit_price_at_sale)}</td>
                  <td style={{ padding: "7px 12px", textAlign: "right", fontFamily: "monospace", fontWeight: 600 }}>{fmt(item.line_total)}</td>
                  <td style={{ padding: "7px 12px", textAlign: "left" }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: item.is_restorable ? "#15803d" : "#dc2626" }}>
                      {item.is_restorable ? "✓ Yes" : "✗ No"}
                    </span>
                    {item.damaged_notes && <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>{item.damaged_notes}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Action buttons for pending + supervisor */}
        {isActionable && (
          <div style={{ display: "flex", gap: 10 }}>
            <button
              onClick={() => onApproveReject(r, "approve")}
              style={{ flex: 1, padding: "10px 0", borderRadius: 8, background: "#15803d", color: "#fff", border: "none", fontWeight: 700, fontSize: 14, cursor: "pointer" }}
            >
              Approve & Refund
            </button>
            <button
              onClick={() => onApproveReject(r, "reject")}
              style={{ flex: 1, padding: "10px 0", borderRadius: 8, background: "#dc2626", color: "#fff", border: "none", fontWeight: 700, fontSize: 14, cursor: "pointer" }}
            >
              Reject Return
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Approve Modal ─────────────────────────────────────────────────────────────

function ApproveModal({ returnData, action, onClose, onDone }) {
  const isMobile = useMobile();
  const [refundMethod, setRefundMethod] = useState("cash");
  const [refundRef, setRefundRef]       = useState("");
  const [notes, setNotes]               = useState("");
  const [rejectNotes, setRejectNotes]   = useState("");
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState(null);

  const isApprove = action === "approve";

  const handleSubmit = async () => {
    setLoading(true); setError(null);
    try {
      if (isApprove) {
        await returnsAPI.approve(returnData.id, {
          refund_method: refundMethod,
          refund_ref:    refundRef || null,
          notes:         notes    || null,
        });
      } else {
        if (!rejectNotes.trim()) { setError("Rejection reason is required."); setLoading(false); return; }
        await returnsAPI.reject(returnData.id, { rejection_notes: rejectNotes });
      }
      onDone();
    } catch (e) {
      setError(e.message || "Action failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 1100, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ background: "#fff", borderRadius: 14, padding: isMobile ? 20 : 28, width: "100%", maxWidth: 460, boxShadow: "0 8px 32px rgba(0,0,0,0.22)" }}>
        <div style={{ fontWeight: 800, fontSize: 16, marginBottom: 4, color: isApprove ? "#15803d" : "#dc2626" }}>
          {isApprove ? "Approve & Issue Refund" : "Reject Return"}
        </div>
        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 20 }}>
          Return <strong>{returnData.return_number}</strong> · Orig. <strong>{returnData.original_txn_number}</strong>
        </div>

        {isApprove ? (
          <>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 11, fontWeight: 700, color: "#334155", display: "block", marginBottom: 6, textTransform: "uppercase" }}>Refund Method *</label>
              <select
                value={refundMethod}
                onChange={(e) => setRefundMethod(e.target.value)}
                style={{ ...shellStyles.searchInput, width: "100%", padding: "9px 12px" }}
              >
                {REFUND_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 11, fontWeight: 700, color: "#334155", display: "block", marginBottom: 6, textTransform: "uppercase" }}>Refund Reference (optional)</label>
              <input
                type="text"
                value={refundRef}
                placeholder="M-PESA ref, card auth code, etc."
                onChange={(e) => setRefundRef(e.target.value)}
                style={{ ...shellStyles.searchInput, width: "100%", padding: "9px 12px" }}
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 11, fontWeight: 700, color: "#334155", display: "block", marginBottom: 6, textTransform: "uppercase" }}>Notes (optional)</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                style={{ ...shellStyles.searchInput, width: "100%", padding: "9px 12px", resize: "vertical" }}
              />
            </div>
          </>
        ) : (
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#334155", display: "block", marginBottom: 6, textTransform: "uppercase" }}>Rejection Reason *</label>
            <textarea
              value={rejectNotes}
              onChange={(e) => setRejectNotes(e.target.value)}
              rows={3}
              placeholder="Explain why this return is being rejected..."
              style={{ ...shellStyles.searchInput, width: "100%", padding: "9px 12px", resize: "vertical" }}
            />
          </div>
        )}

        {error && (
          <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "8px 12px", marginBottom: 14, fontSize: 12, color: "#dc2626" }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10 }}>
          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{
              flex: 1, padding: "10px 0", borderRadius: 8, border: "none", fontWeight: 700, fontSize: 14, cursor: "pointer",
              background: loading ? "#94a3b8" : isApprove ? "#15803d" : "#dc2626",
              color: "#fff",
            }}
          >
            {loading ? "Processing..." : isApprove ? "Confirm Refund" : "Confirm Rejection"}
          </button>
          <button
            onClick={onClose}
            disabled={loading}
            style={{ padding: "10px 20px", borderRadius: 8, border: "1px solid #e2e8f0", background: "#f8fafc", fontWeight: 600, cursor: "pointer", color: "#475569" }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Create Return Form ────────────────────────────────────────────────────────

function CreateReturnForm({ onClose, onCreated }) {
  const isMobile = useMobile();
  const [step, setStep]           = useState("lookup"); // lookup | items | confirm
  const [txnSearch, setTxnSearch] = useState("");
  const [txnData, setTxnData]     = useState(null);
  const [lookupError, setLookupError] = useState(null);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [selectedItems, setSelectedItems] = useState({});
  // selectedItems: { [txn_item_id]: { qty: number, is_restorable: bool, damaged_notes: string } }
  const [reason, setReason]       = useState("change_of_mind");
  const [reasonNotes, setReasonNotes] = useState("");
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const lookupTransaction = async () => {
    if (!txnSearch.trim()) return;
    setLookupLoading(true); setLookupError(null); setTxnData(null);
    try {
      // Try searching by txn_number
      const result = await transactionsAPI?.getByNumber?.(txnSearch.trim())
        || await transactionsAPI?.list?.({ search: txnSearch.trim(), limit: 1 })
          .then((r) => Array.isArray(r) ? r[0] : r?.items?.[0]);
      if (!result) throw new Error("Transaction not found");
      if (result.status !== "completed") throw new Error(`Transaction is ${result.status} — only COMPLETED transactions can be returned.`);
      setTxnData(result);
      setStep("items");
    } catch (e) {
      setLookupError(e.message || "Transaction not found");
    } finally {
      setLookupLoading(false);
    }
  };

  const toggleItem = (itemId, maxQty) => {
    setSelectedItems((prev) => {
      if (prev[itemId]) {
        const n = { ...prev }; delete n[itemId]; return n;
      }
      return { ...prev, [itemId]: { qty: maxQty, is_restorable: true, damaged_notes: "" } };
    });
  };

  const updateItemField = (itemId, field, value) => {
    setSelectedItems((prev) => ({ ...prev, [itemId]: { ...prev[itemId], [field]: value } }));
  };

  const handleSubmit = async () => {
    const itemEntries = Object.entries(selectedItems);
    if (itemEntries.length === 0) { setSubmitError("Select at least one item to return."); return; }

    setSubmitLoading(true); setSubmitError(null);
    try {
      const payload = {
        original_txn_id: txnData.id,
        return_reason:   reason,
        reason_notes:    reasonNotes || null,
        items: itemEntries.map(([id, d]) => ({
          original_txn_item_id: parseInt(id),
          qty_returned:         parseInt(d.qty),
          is_restorable:        d.is_restorable,
          damaged_notes:        d.damaged_notes || null,
        })),
      };
      await returnsAPI.create(payload);
      onCreated();
    } catch (e) {
      setSubmitError(e.message || "Failed to create return");
    } finally {
      setSubmitLoading(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 1000, display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
      <div style={{
        background: "#fff", borderRadius: "16px 16px 0 0", width: "100%", maxWidth: 680,
        maxHeight: "92vh", overflowY: "auto", padding: isMobile ? 16 : 28,
        boxShadow: "0 -8px 32px rgba(0,0,0,0.18)",
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div style={{ fontWeight: 800, fontSize: isMobile ? 15 : 18 }}>Initiate Return</div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 22, cursor: "pointer", color: "#94a3b8" }}>×</button>
        </div>

        {/* Step: Lookup */}
        {step === "lookup" && (
          <>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, fontWeight: 700, color: "#334155", display: "block", marginBottom: 6, textTransform: "uppercase" }}>Transaction Number</label>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  type="text"
                  value={txnSearch}
                  placeholder="e.g. TXN-XXXXXXXX"
                  onChange={(e) => setTxnSearch(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && lookupTransaction()}
                  style={{ ...shellStyles.searchInput, flex: 1, padding: "9px 12px" }}
                />
                <button
                  onClick={lookupTransaction}
                  disabled={lookupLoading}
                  style={{ ...shellStyles.smallButton(isMobile), padding: "9px 18px", background: "#1b6cff", color: "#fff", borderColor: "#1b6cff" }}
                >
                  {lookupLoading ? "..." : "Lookup"}
                </button>
              </div>
            </div>
            {lookupError && (
              <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#dc2626" }}>
                {lookupError}
              </div>
            )}
          </>
        )}

        {/* Step: Select items */}
        {step === "items" && txnData && (
          <>
            <div style={{ background: "#f0f7ff", border: "1px solid #bfdbfe", borderRadius: 8, padding: "10px 14px", marginBottom: 16, fontSize: 13 }}>
              <strong>TXN:</strong> {txnData.txn_number}&nbsp;·&nbsp;
              <strong>Total:</strong> {fmt(txnData.total)}&nbsp;·&nbsp;
              <strong>Date:</strong> {new Date(txnData.created_at).toLocaleDateString("en-KE")}
            </div>

            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 10, color: "#334155" }}>Select Items to Return</div>
            {(txnData.items || []).map((item) => {
              const sel = selectedItems[item.id];
              return (
                <div key={item.id} style={{
                  border: `1px solid ${sel ? "#bfdbfe" : "#e2e8f0"}`,
                  borderRadius: 8, padding: "12px 14px", marginBottom: 10,
                  background: sel ? "#f0f7ff" : "#fafafa",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <label style={{ display: "flex", gap: 10, alignItems: "center", cursor: "pointer", flex: 1 }}>
                      <input type="checkbox" checked={!!sel} onChange={() => toggleItem(item.id, item.qty)} />
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13 }}>{item.product_name}</div>
                        <div style={{ fontSize: 11, color: "#64748b" }}>{item.sku} · Qty sold: {item.qty} · {fmt(item.unit_price)}</div>
                      </div>
                    </label>
                    <div style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 13 }}>{fmt(item.line_total)}</div>
                  </div>

                  {sel && (
                    <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: isMobile ? "1fr" : "120px 1fr 1fr", gap: 8 }}>
                      <div>
                        <label style={{ fontSize: 10, fontWeight: 700, color: "#64748b", display: "block", marginBottom: 4, textTransform: "uppercase" }}>Qty to Return</label>
                        <input
                          type="number"
                          min={1} max={item.qty}
                          value={sel.qty}
                          onChange={(e) => updateItemField(item.id, "qty", Math.min(Math.max(1, parseInt(e.target.value) || 1), item.qty))}
                          style={{ ...shellStyles.searchInput, width: "100%", padding: "6px 10px" }}
                        />
                      </div>
                      <div>
                        <label style={{ fontSize: 10, fontWeight: 700, color: "#64748b", display: "block", marginBottom: 4, textTransform: "uppercase" }}>Restorable to Stock?</label>
                        <select
                          value={sel.is_restorable ? "yes" : "no"}
                          onChange={(e) => updateItemField(item.id, "is_restorable", e.target.value === "yes")}
                          style={{ ...shellStyles.searchInput, width: "100%", padding: "6px 10px" }}
                        >
                          <option value="yes">Yes — goes back to stock</option>
                          <option value="no">No — damaged / write-off</option>
                        </select>
                      </div>
                      {!sel.is_restorable && (
                        <div>
                          <label style={{ fontSize: 10, fontWeight: 700, color: "#64748b", display: "block", marginBottom: 4, textTransform: "uppercase" }}>Damage Notes</label>
                          <input
                            type="text"
                            value={sel.damaged_notes}
                            placeholder="Optional notes..."
                            onChange={(e) => updateItemField(item.id, "damaged_notes", e.target.value)}
                            style={{ ...shellStyles.searchInput, width: "100%", padding: "6px 10px" }}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Reason */}
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 12, marginTop: 16 }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 700, color: "#334155", display: "block", marginBottom: 6, textTransform: "uppercase" }}>Return Reason *</label>
                <select
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  style={{ ...shellStyles.searchInput, width: "100%", padding: "9px 12px" }}
                >
                  {RETURN_REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 700, color: "#334155", display: "block", marginBottom: 6, textTransform: "uppercase" }}>Notes (optional)</label>
                <input
                  type="text"
                  value={reasonNotes}
                  onChange={(e) => setReasonNotes(e.target.value)}
                  placeholder="Additional context..."
                  style={{ ...shellStyles.searchInput, width: "100%", padding: "9px 12px" }}
                />
              </div>
            </div>

            {submitError && (
              <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "10px 14px", marginTop: 12, fontSize: 13, color: "#dc2626" }}>
                {submitError}
              </div>
            )}

            <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
              <button
                onClick={handleSubmit}
                disabled={submitLoading || Object.keys(selectedItems).length === 0}
                style={{
                  flex: 1, padding: "11px 0", borderRadius: 8, border: "none",
                  background: submitLoading ? "#94a3b8" : "#1b6cff",
                  color: "#fff", fontWeight: 700, fontSize: 14, cursor: "pointer",
                }}
              >
                {submitLoading ? "Submitting..." : `Submit Return (${Object.keys(selectedItems).length} item${Object.keys(selectedItems).length !== 1 ? "s" : ""})`}
              </button>
              <button
                onClick={() => setStep("lookup")}
                style={{ padding: "11px 20px", borderRadius: 8, border: "1px solid #e2e8f0", background: "#f8fafc", cursor: "pointer", color: "#475569", fontWeight: 600 }}
              >
                Back
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Root Component ────────────────────────────────────────────────────────────

export default function ReturnsTab() {
  const [view, setView]           = useState("list");  // list | create | detail
  const [selectedReturn, setSelectedReturn] = useState(null);
  const [approveAction, setApproveAction] = useState(null); // { returnData, action }
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = () => setRefreshKey((k) => k + 1);

  const handleSelectReturn = (r) => {
    setSelectedReturn(r);
    setView("detail");
  };

  const handleApproveReject = (returnData, action) => {
    setApproveAction({ returnData, action });
  };

  const handleApprovalDone = () => {
    setApproveAction(null);
    setSelectedReturn(null);
    setView("list");
    refresh();
  };

  const handleCreated = () => {
    setView("list");
    refresh();
  };

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <ReturnsList
        onSelect={handleSelectReturn}
        onCreateNew={() => setView("create")}
        refreshKey={refreshKey}
      />

      {view === "detail" && selectedReturn && (
        <ReturnDetail
          returnId={selectedReturn.id}
          onClose={() => { setSelectedReturn(null); setView("list"); }}
          onApproveReject={handleApproveReject}
          refreshKey={refreshKey}
        />
      )}

      {view === "create" && (
        <CreateReturnForm
          onClose={() => setView("list")}
          onCreated={handleCreated}
        />
      )}

      {approveAction && (
        <ApproveModal
          returnData={approveAction.returnData}
          action={approveAction.action}
          onClose={() => setApproveAction(null)}
          onDone={handleApprovalDone}
        />
      )}
    </div>
  );
}
