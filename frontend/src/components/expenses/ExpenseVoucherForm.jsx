/**
 * ExpenseVoucherForm — create a new expense voucher.
 * Loads the chart of accounts (EXPENSE type) for the account picker.
 * Validates required fields client-side before API call.
 */
import { useState, useEffect } from "react";
import { expensesAPI, accountingAPI } from "../../api/client";
import { shellStyles } from "../backoffice/styles";
import { Section, EmptyState } from "../backoffice/UIComponents";

const PM_OPTIONS = [
  { value:"cash",   label:"Cash" },
  { value:"mpesa",  label:"M-PESA" },
  { value:"card",   label:"Card" },
  { value:"bank",   label:"Bank Transfer" },
  { value:"cheque", label:"Cheque" },
];

function today() { return new Date().toISOString().slice(0, 10); }

function useMobile() {
  const [m, setM] = useState(typeof window !== "undefined" && window.innerWidth < 768);
  useEffect(() => { const h = () => setM(window.innerWidth < 768); window.addEventListener("resize", h); return () => window.removeEventListener("resize", h); }, []);
  return m;
}

export default function ExpenseVoucherForm({ onSaved, onBack }) {
  const isMobile = useMobile();
  const [accounts, setAccounts] = useState([]);
  const [form, setForm] = useState({
    expense_date: today(),
    account_id: "",
    amount: "",
    payment_method: "cash",
    payee: "",
    reference: "",
    notes: "",
  });
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState(null);

  useEffect(() => {
    accountingAPI.accounts({ account_type: "EXPENSE" })
      .then(data => setAccounts(Array.isArray(data) ? data : []))
      .catch(() => setAccounts([]));
  }, []);

  const set = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
    if (errors[field]) setErrors(prev => { const n={...prev}; delete n[field]; return n; });
  };

  const validate = () => {
    const e = {};
    if (!form.expense_date)   e.expense_date = "Date is required";
    if (!form.account_id)     e.account_id = "Account is required";
    if (!form.amount || isNaN(Number(form.amount)) || Number(form.amount) <= 0) e.amount = "Valid positive amount required";
    if (!form.payment_method) e.payment_method = "Payment method is required";
    return e;
  };

  const handleSubmit = async () => {
    const e = validate();
    if (Object.keys(e).length > 0) { setErrors(e); return; }
    setSubmitting(true); setApiError(null);
    try {
      const row = await expensesAPI.create({
        expense_date:   form.expense_date,
        account_id:     Number(form.account_id),
        amount:         Number(form.amount),
        payment_method: form.payment_method,
        payee:          form.payee   || null,
        reference:      form.reference || null,
        notes:          form.notes   || null,
      });
      onSaved?.(row);
    } catch (err) {
      setApiError(err.message || "Failed to create expense voucher");
    } finally {
      setSubmitting(false);
    }
  };

  const inp = (field) => ({
    style: { ...shellStyles.searchInput, width:"100%", padding:"9px 12px",
      borderColor: errors[field] ? "#fca5a5" : undefined },
  });

  return (
    <Section
      title="New Expense Voucher"
      right={
        <button onClick={onBack} style={{ ...shellStyles.smallButton(isMobile), color:"#64748b" }}>
          ← Back to List
        </button>
      }
    >
      <div style={{ display:"grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap:16, maxWidth:720 }}>

        {/* Date */}
        <div>
          <label style={{ fontSize:11,fontWeight:700,color:"#334155",display:"block",marginBottom:6,textTransform:"uppercase" }}>
            Expense Date *
          </label>
          <input type="date" value={form.expense_date} onChange={e=>set("expense_date",e.target.value)} {...inp("expense_date")} />
          {errors.expense_date && <div style={{ fontSize:11,color:"#dc2626",marginTop:4 }}>{errors.expense_date}</div>}
        </div>

        {/* Account */}
        <div>
          <label style={{ fontSize:11,fontWeight:700,color:"#334155",display:"block",marginBottom:6,textTransform:"uppercase" }}>
            Expense Account *
          </label>
          <select
            value={form.account_id}
            onChange={e=>set("account_id",e.target.value)}
            style={{ ...shellStyles.searchInput, width:"100%", padding:"9px 12px", borderColor: errors.account_id?"#fca5a5":undefined }}
          >
            <option value="">Select account...</option>
            {accounts.map(a => (
              <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
            ))}
            {accounts.length === 0 && <option disabled>No expense accounts found — seed accounts first</option>}
          </select>
          {errors.account_id && <div style={{ fontSize:11,color:"#dc2626",marginTop:4 }}>{errors.account_id}</div>}
        </div>

        {/* Amount */}
        <div>
          <label style={{ fontSize:11,fontWeight:700,color:"#334155",display:"block",marginBottom:6,textTransform:"uppercase" }}>
            Amount (KES) *
          </label>
          <input
            type="number" min="0.01" step="0.01"
            placeholder="0.00"
            value={form.amount} onChange={e=>set("amount",e.target.value)}
            {...inp("amount")}
          />
          {errors.amount && <div style={{ fontSize:11,color:"#dc2626",marginTop:4 }}>{errors.amount}</div>}
        </div>

        {/* Payment Method */}
        <div>
          <label style={{ fontSize:11,fontWeight:700,color:"#334155",display:"block",marginBottom:6,textTransform:"uppercase" }}>
            Payment Method *
          </label>
          <select value={form.payment_method} onChange={e=>set("payment_method",e.target.value)}
            style={{ ...shellStyles.searchInput,width:"100%",padding:"9px 12px",borderColor:errors.payment_method?"#fca5a5":undefined }}>
            {PM_OPTIONS.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          {errors.payment_method && <div style={{ fontSize:11,color:"#dc2626",marginTop:4 }}>{errors.payment_method}</div>}
        </div>

        {/* Payee */}
        <div>
          <label style={{ fontSize:11,fontWeight:700,color:"#334155",display:"block",marginBottom:6,textTransform:"uppercase" }}>
            Payee / Vendor
          </label>
          <input type="text" placeholder="Who was paid?" value={form.payee} onChange={e=>set("payee",e.target.value)} {...inp("payee")} />
        </div>

        {/* Reference */}
        <div>
          <label style={{ fontSize:11,fontWeight:700,color:"#334155",display:"block",marginBottom:6,textTransform:"uppercase" }}>
            Reference / Receipt #
          </label>
          <input type="text" placeholder="Receipt or invoice number" value={form.reference} onChange={e=>set("reference",e.target.value)} {...inp("reference")} />
        </div>

        {/* Notes — full width */}
        <div style={{ gridColumn: isMobile ? "1" : "1 / -1" }}>
          <label style={{ fontSize:11,fontWeight:700,color:"#334155",display:"block",marginBottom:6,textTransform:"uppercase" }}>
            Notes
          </label>
          <textarea
            rows={3} placeholder="Optional description..."
            value={form.notes} onChange={e=>set("notes",e.target.value)}
            style={{ ...shellStyles.searchInput,width:"100%",padding:"9px 12px",resize:"vertical" }}
          />
        </div>
      </div>

      {apiError && (
        <div style={{ background:"#fef2f2",border:"1px solid #fca5a5",borderRadius:8,padding:"10px 14px",marginTop:16,fontSize:13,color:"#dc2626" }}>
          {apiError}
        </div>
      )}

      <div style={{ display:"flex",gap:12,marginTop:20 }}>
        <button
          onClick={handleSubmit}
          disabled={submitting}
          style={{ padding:"11px 32px",borderRadius:8,border:"none",background:submitting?"#94a3b8":"#1b6cff",color:"#fff",fontWeight:700,fontSize:14,cursor:"pointer" }}
        >
          {submitting ? "Saving..." : "Save Voucher"}
        </button>
        <button
          onClick={onBack}
          disabled={submitting}
          style={{ padding:"11px 20px",borderRadius:8,border:"1px solid #e2e8f0",background:"#f8fafc",cursor:"pointer",color:"#475569",fontWeight:600 }}
        >
          Cancel
        </button>
      </div>
    </Section>
  );
}
