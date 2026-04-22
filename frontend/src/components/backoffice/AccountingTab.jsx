/**
 * AccountingTab — Double-entry accounting module UI
 *
 * Views (sub-tabs):
 *   P&L           — Profit & Loss for a date range
 *   Balance Sheet — Assets = Liabilities + Equity
 *   VAT           — VAT output/input reconciliation for KRA
 *   Trial Balance — All account balances, confirms books are balanced
 *   Accounts      — Chart of accounts with ledger drill-down
 *   Journal       — Raw journal entry log
 *
 * Access: Manager + Admin only (enforced at API level too)
 */

import { useState, useEffect, useCallback } from "react";
import { fmtKES, accountingAPI } from "../../api/client";
import { Section, EmptyState, KPIBox } from "./UIComponents";
import { shellStyles } from "./styles";
import APAgingView from "../accounting/APAgingView";
import ARAgingView from "../accounting/ARAgingView";
import SupplierStatementView from "../accounting/SupplierStatementView";
import CustomerStatementView from "../accounting/CustomerStatementView";
import ConsolidatedPLView from "../accounting/ConsolidatedPLView";
import BranchComparisonView from "../accounting/BranchComparisonView";

// ── Shared style helpers ──────────────────────────────────────────────────────

const fmt  = (v) => fmtKES(v ?? 0);
const pct  = (v, t) => t ? `${((v / t) * 100).toFixed(1)}%` : "—";
const pos  = (v) => (v ?? 0) >= 0;

const ACCENT = {
  revenue:  "#15803d",
  cogs:     "#b45309",
  expense:  "#dc2626",
  profit:   "#1b6cff",
  asset:    "#155eef",
  liability:"#dc2626",
  equity:   "#15803d",
  vat:      "#7c3aed",
  neutral:  "#64748b",
};

const pill = (color, text) => (
  <span style={{
    background: color + "22",
    color,
    border: `1px solid ${color}55`,
    borderRadius: 20,
    padding: "2px 10px",
    fontSize: 11,
    fontWeight: 700,
  }}>{text}</span>
);

// ── Date range helper ─────────────────────────────────────────────────────────

function today() {
  return new Date().toISOString().slice(0, 10);
}

function firstOfMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function DateRange({ from, to, onChange }) {
  const [isMobile] = useMobile();
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <label style={{ fontSize: 11, color: "#64748b", fontWeight: 700 }}>FROM</label>
      <input
        type="date" value={from}
        onChange={(e) => onChange({ from: e.target.value, to })}
        style={{ ...shellStyles.searchInput, width: 130, padding: "6px 10px", fontSize: 12 }}
      />
      <label style={{ fontSize: 11, color: "#64748b", fontWeight: 700 }}>TO</label>
      <input
        type="date" value={to}
        onChange={(e) => onChange({ from, to: e.target.value })}
        style={{ ...shellStyles.searchInput, width: 130, padding: "6px 10px", fontSize: 12 }}
      />
    </div>
  );
}

function useMobile() {
  const [isMobile, setIsMobile] = useState(
    typeof window !== "undefined" && window.innerWidth < 768
  );
  useEffect(() => {
    const h = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", h);
    return () => window.removeEventListener("resize", h);
  }, []);
  return [isMobile];
}

// ── Amount row used in all statements ────────────────────────────────────────

function AmountRow({ label, amount, bold, color, indent, border }) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "1fr auto",
      padding: "7px 0",
      paddingLeft: indent ? 20 : 0,
      borderTop: border ? "1px solid #e2e8f0" : "none",
      fontWeight: bold ? 700 : 400,
      fontSize: 13,
      color: color || "#1e293b",
    }}>
      <span style={{ color: bold ? "#0f172a" : "#334155" }}>{label}</span>
      <span style={{ fontFamily: "monospace", color: color || (bold ? "#0f172a" : "#334155") }}>
        {fmt(amount)}
      </span>
    </div>
  );
}

function Divider() {
  return <div style={{ borderTop: "2px solid #cbd5e1", margin: "4px 0" }} />;
}

// ── P&L VIEW ─────────────────────────────────────────────────────────────────

function PLView() {
  const [isMobile] = useMobile();
  const [range, setRange] = useState({ from: firstOfMonth(), to: today() });
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      setData(await accountingAPI.pl({ date_from: range.from, date_to: range.to }));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [range.from, range.to]);

  useEffect(() => { load(); }, [load]);

  return (
    <div style={{ display: "grid", gap: isMobile ? 12 : 16 }}>
      {/* KPI strip */}
      {data && (
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(2,1fr)" : "repeat(4,1fr)", gap: isMobile ? 8 : 12 }}>
          <KPIBox label="Revenue"      value={fmt(data.revenue)}      accent={ACCENT.revenue}  sub="total sales" />
          <KPIBox label="COGS"         value={fmt(data.cogs)}          accent={ACCENT.cogs}     sub="cost of goods" />
          <KPIBox label="Gross Profit" value={fmt(data.gross_profit)}  accent={ACCENT.profit}   sub={pct(data.gross_profit, data.revenue) + " margin"} />
          <KPIBox label="Net Profit"   value={fmt(data.net_profit)}    accent={pos(data.net_profit) ? ACCENT.profit : ACCENT.expense}
                  sub={pct(data.net_profit, data.revenue) + " margin"} />
        </div>
      )}

      <Section
        title="Profit & Loss Statement"
        right={<DateRange from={range.from} to={range.to} onChange={setRange} />}
      >
        {loading && <EmptyState text="Loading P&L..." />}
        {error   && <EmptyState text={`Error: ${error}`} />}
        {data && !loading && (
          <div style={{ maxWidth: 560 }}>
            {/* Revenue */}
            <div style={{ fontWeight: 700, fontSize: 11, color: ACCENT.revenue, letterSpacing: ".08em", textTransform: "uppercase", marginBottom: 4 }}>Revenue</div>
            {(data.breakdown?.revenue || []).map((r) => (
              <AmountRow key={r.code} label={`${r.code} — ${r.name}`} amount={r.amount} indent />
            ))}
            <AmountRow label="Total Revenue" amount={data.revenue} bold border />
            <Divider />

            {/* COGS */}
            <div style={{ fontWeight: 700, fontSize: 11, color: ACCENT.cogs, letterSpacing: ".08em", textTransform: "uppercase", margin: "12px 0 4px" }}>Cost of Goods Sold</div>
            {(data.breakdown?.cogs || []).map((r) => (
              <AmountRow key={r.code} label={`${r.code} — ${r.name}`} amount={r.amount} indent />
            ))}
            <AmountRow label="Total COGS" amount={data.cogs} bold border />
            <Divider />

            <AmountRow label="Gross Profit" amount={data.gross_profit} bold
              color={pos(data.gross_profit) ? ACCENT.revenue : ACCENT.expense} border />
            <Divider />

            {/* Expenses */}
            <div style={{ fontWeight: 700, fontSize: 11, color: ACCENT.expense, letterSpacing: ".08em", textTransform: "uppercase", margin: "12px 0 4px" }}>Operating Expenses</div>
            {(data.breakdown?.expenses || []).map((r) => (
              <AmountRow key={r.code} label={`${r.code} — ${r.name}`} amount={r.amount} indent />
            ))}
            {(!data.breakdown?.expenses?.length) && (
              <div style={{ fontSize: 12, color: "#94a3b8", padding: "8px 0 8px 20px" }}>
                No expense accounts have been posted yet.
              </div>
            )}
            <AmountRow label="Total Expenses" amount={data.expenses} bold border />
            <Divider />

            <AmountRow
              label="Net Profit / (Loss)"
              amount={data.net_profit}
              bold border
              color={pos(data.net_profit) ? ACCENT.revenue : ACCENT.expense}
            />
          </div>
        )}
      </Section>
    </div>
  );
}

// ── BALANCE SHEET VIEW ────────────────────────────────────────────────────────

function BalanceSheetView() {
  const [isMobile] = useMobile();
  const [asOf, setAsOf]     = useState(today());
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await accountingAPI.balanceSheet({ as_of_date: asOf })); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [asOf]);

  useEffect(() => { load(); }, [load]);

  const BalanceSection = ({ title, items, total, color }) => (
    <>
      <div style={{ fontWeight: 700, fontSize: 11, color, letterSpacing: ".08em", textTransform: "uppercase", margin: "12px 0 4px" }}>{title}</div>
      {items.map((r) => <AmountRow key={r.code} label={`${r.code} — ${r.name}`} amount={r.amount} indent />)}
      {!items.length && <div style={{ fontSize: 12, color: "#94a3b8", padding: "4px 0 4px 20px" }}>No entries yet</div>}
      <AmountRow label={`Total ${title}`} amount={total} bold border />
      <Divider />
    </>
  );

  return (
    <Section
      title="Balance Sheet"
      right={
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 11, color: "#64748b", fontWeight: 700 }}>AS OF</label>
          <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)}
            style={{ ...shellStyles.searchInput, width: 130, padding: "6px 10px", fontSize: 12 }} />
        </div>
      }
    >
      {loading && <EmptyState text="Loading balance sheet..." />}
      {error   && <EmptyState text={`Error: ${error}`} />}
      {data && !loading && (
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 32 }}>
          {/* Left column — Assets */}
          <div>
            <BalanceSection title="Assets" items={data.assets} total={data.total_assets} color={ACCENT.asset} />
          </div>

          {/* Right column — Liabilities + Equity */}
          <div>
            <BalanceSection title="Liabilities" items={data.liabilities} total={data.total_liabilities} color={ACCENT.liability} />
            <BalanceSection title="Equity" items={data.equity} total={data.total_equity} color={ACCENT.equity} />
            <AmountRow label="Total Liabilities + Equity" amount={data.total_liabilities + data.total_equity} bold border />

            <div style={{ marginTop: 12, padding: "8px 12px", borderRadius: 8,
              background: data.is_balanced ? "#f0fdf4" : "#fef2f2",
              border: `1px solid ${data.is_balanced ? "#bbf7d0" : "#fecaca"}`,
              fontSize: 12, fontWeight: 700,
              color: data.is_balanced ? "#15803d" : "#dc2626" }}>
              {data.is_balanced ? "✓ Books balanced" : "⚠ Books NOT balanced — contact support"}
            </div>
          </div>
        </div>
      )}
    </Section>
  );
}

// ── VAT VIEW ──────────────────────────────────────────────────────────────────

function VATView() {
  const [isMobile] = useMobile();
  const [range, setRange] = useState({ from: firstOfMonth(), to: today() });
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await accountingAPI.vat({ date_from: range.from, date_to: range.to })); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [range.from, range.to]);

  useEffect(() => { load(); }, [load]);

  return (
    <div style={{ display: "grid", gap: isMobile ? 12 : 16 }}>
      {data && (
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(2,1fr)" : "repeat(3,1fr)", gap: isMobile ? 8 : 12 }}>
          <KPIBox label="Output VAT (Sales)"     value={fmt(data.output_vat)} accent={ACCENT.vat}     sub="collected from customers" />
          <KPIBox label="Input VAT (Purchases)"  value={fmt(data.input_vat)}  accent={ACCENT.neutral} sub="paid to suppliers" />
          <KPIBox label="Net VAT Payable to KRA" value={fmt(data.net_payable)} accent={ACCENT.expense} sub={`${data.vat_rate} standard rate`} />
        </div>
      )}

      <Section
        title="VAT Reconciliation"
        right={<DateRange from={range.from} to={range.to} onChange={setRange} />}
      >
        {loading && <EmptyState text="Loading VAT summary..." />}
        {error   && <EmptyState text={`Error: ${error}`} />}
        {data && !loading && (
          <div style={{ maxWidth: 480 }}>
            <AmountRow label="Output VAT (collected on sales)"       amount={data.output_vat}  />
            <AmountRow label="Input VAT (paid on purchases)"         amount={data.input_vat}   />
            <Divider />
            <AmountRow label="Net VAT Payable to KRA" amount={data.net_payable} bold
              color={data.net_payable > 0 ? ACCENT.expense : ACCENT.revenue} border />

            {data.note && (
              <div style={{ marginTop: 16, padding: "10px 14px", borderRadius: 8,
                background: "#fffbeb", border: "1px solid #fde68a",
                fontSize: 12, color: "#92400e" }}>
                ℹ {data.note}
              </div>
            )}

            <div style={{ marginTop: 16, padding: "12px 14px", borderRadius: 8,
              background: "#f8fafc", border: "1px solid #e2e8f0",
              fontSize: 12, color: "#475569" }}>
              <strong>Filing reminder:</strong> VAT returns are due by the 20th of the following month.
              File via <a href="https://itax.kra.go.ke" target="_blank" rel="noreferrer"
                style={{ color: "#1b6cff" }}>iTax</a> or through your eTIMS dashboard.
            </div>
          </div>
        )}
      </Section>
    </div>
  );
}

// ── TRIAL BALANCE VIEW ────────────────────────────────────────────────────────

function TrialBalanceView() {
  const [isMobile] = useMobile();
  const [asOf, setAsOf]     = useState(today());
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await accountingAPI.trialBalance({ as_of_date: asOf })); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [asOf]);

  useEffect(() => { load(); }, [load]);

  const typeColor = (t) => ({
    ASSET: ACCENT.asset, LIABILITY: ACCENT.liability, EQUITY: ACCENT.equity,
    REVENUE: ACCENT.revenue, COGS: ACCENT.cogs, EXPENSE: ACCENT.expense,
  }[t] || ACCENT.neutral);

  return (
    <Section
      title="Trial Balance"
      right={
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 11, color: "#64748b", fontWeight: 700 }}>AS OF</label>
          <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)}
            style={{ ...shellStyles.searchInput, width: 130, padding: "6px 10px", fontSize: 12 }} />
        </div>
      }
    >
      {loading && <EmptyState text="Loading trial balance..." />}
      {error   && <EmptyState text={`Error: ${error}`} />}
      {data && !loading && (
        <>
          {/* Balance indicator */}
          <div style={{ marginBottom: 16, padding: "8px 14px", borderRadius: 8, display: "inline-flex", gap: 12, alignItems: "center",
            background: data.is_balanced ? "#f0fdf4" : "#fef2f2",
            border: `1px solid ${data.is_balanced ? "#bbf7d0" : "#fecaca"}` }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: data.is_balanced ? "#15803d" : "#dc2626" }}>
              {data.is_balanced ? "✓ Balanced" : "⚠ Out of balance"}
            </span>
            <span style={{ fontSize: 12, color: "#64748b" }}>
              DR: {fmt(data.total_debits)} | CR: {fmt(data.total_credits)}
            </span>
          </div>

          {/* Table */}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: isMobile ? 11 : 13 }}>
              <thead>
                <tr style={{ background: "#edf4ff", borderBottom: "2px solid #bfdbfe" }}>
                  {["Code", "Account Name", "Type", "Debit Balance", "Credit Balance"].map((h) => (
                    <th key={h} style={{ textAlign: h.includes("Balance") ? "right" : "left",
                      padding: isMobile ? "6px 8px" : "9px 12px", fontWeight: 700,
                      fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em",
                      color: "#334155" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.accounts.map((acc, i) => (
                  <tr key={acc.code} style={{ background: i % 2 === 0 ? "#fff" : "#f8fafc",
                    borderBottom: "1px solid #e2e8f0" }}>
                    <td style={{ padding: isMobile ? "5px 8px" : "8px 12px", fontFamily: "monospace", fontWeight: 700 }}>{acc.code}</td>
                    <td style={{ padding: isMobile ? "5px 8px" : "8px 12px", color: "#1e293b" }}>{acc.name}</td>
                    <td style={{ padding: isMobile ? "5px 8px" : "8px 12px" }}>
                      {pill(typeColor(acc.account_type), acc.account_type)}
                    </td>
                    <td style={{ padding: isMobile ? "5px 8px" : "8px 12px", textAlign: "right", fontFamily: "monospace",
                      color: acc.debit_balance > 0 ? "#1e293b" : "#94a3b8" }}>
                      {acc.debit_balance > 0 ? fmt(acc.debit_balance) : "—"}
                    </td>
                    <td style={{ padding: isMobile ? "5px 8px" : "8px 12px", textAlign: "right", fontFamily: "monospace",
                      color: acc.credit_balance > 0 ? "#1e293b" : "#94a3b8" }}>
                      {acc.credit_balance > 0 ? fmt(acc.credit_balance) : "—"}
                    </td>
                  </tr>
                ))}
                {/* Totals row */}
                <tr style={{ background: "#edf4ff", borderTop: "2px solid #bfdbfe", fontWeight: 700 }}>
                  <td colSpan={3} style={{ padding: isMobile ? "7px 8px" : "10px 12px", textTransform: "uppercase", fontSize: 11 }}>Totals</td>
                  <td style={{ padding: isMobile ? "7px 8px" : "10px 12px", textAlign: "right", fontFamily: "monospace" }}>{fmt(data.total_debits)}</td>
                  <td style={{ padding: isMobile ? "7px 8px" : "10px 12px", textAlign: "right", fontFamily: "monospace" }}>{fmt(data.total_credits)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </Section>
  );
}

// ── CHART OF ACCOUNTS VIEW ────────────────────────────────────────────────────

function AccountsView() {
  const [isMobile] = useMobile();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [ledger, setLedger]     = useState(null);  // { account, data }
  const [seeding, setSeeding]   = useState(false);
  const [filter, setFilter]     = useState("ALL");
  const [showCreate, setShowCreate] = useState(false);
  const [newAcct, setNewAcct]   = useState({ code: "", name: "", account_type: "EXPENSE", sub_type: "", description: "" });
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setAccounts(await accountingAPI.accounts()); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSeed = async () => {
    setSeeding(true);
    try {
      const res = await accountingAPI.seed();
      alert(res.message);
      load();
    } catch (e) { alert(e.message); }
    finally { setSeeding(false); }
  };

  const openLedger = async (acc) => {
    setLedger({ account: acc, data: null, loading: true });
    try {
      const data = await accountingAPI.ledger(acc.id);
      setLedger({ account: acc, data, loading: false });
    } catch (e) {
      setLedger({ account: acc, data: null, loading: false, error: e.message });
    }
  };

  const handleCreate = async () => {
    if (!newAcct.code || !newAcct.name) { alert("Code and name are required"); return; }
    setCreating(true);
    try {
      await accountingAPI.createAccount(newAcct);
      setShowCreate(false);
      setNewAcct({ code: "", name: "", account_type: "EXPENSE", sub_type: "", description: "" });
      load();
    } catch (e) { alert(e.message); }
    finally { setCreating(false); }
  };

  const TYPE_OPTIONS = ["ALL", "ASSET", "LIABILITY", "EQUITY", "REVENUE", "COGS", "EXPENSE"];
  const typeColor = (t) => ({ ASSET: ACCENT.asset, LIABILITY: ACCENT.liability, EQUITY: ACCENT.equity,
    REVENUE: ACCENT.revenue, COGS: ACCENT.cogs, EXPENSE: ACCENT.expense }[t] || ACCENT.neutral);

  const filtered = filter === "ALL" ? accounts : accounts.filter((a) => a.account_type === filter);

  if (ledger) {
    return (
      <Section
        title={`Ledger — ${ledger.account.code} ${ledger.account.name}`}
        right={
          <button onClick={() => setLedger(null)} style={shellStyles.smallButton(isMobile)}>
            ← Back to Accounts
          </button>
        }
      >
        {ledger.loading && <EmptyState text="Loading ledger..." />}
        {ledger.error   && <EmptyState text={`Error: ${ledger.error}`} />}
        {ledger.data && !ledger.loading && (
          <>
            <div style={{ marginBottom: 12, fontSize: 13, color: "#475569" }}>
              Closing balance: <strong style={{ fontFamily: "monospace" }}>{fmt(ledger.data.closing_balance)}</strong>
              {" · "}{ledger.data.date_from} to {ledger.data.date_to}
            </div>
            {ledger.data.entries.length === 0 ? (
              <EmptyState text="No transactions in this period." />
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: isMobile ? 11 : 13 }}>
                  <thead>
                    <tr style={{ background: "#edf4ff", borderBottom: "2px solid #bfdbfe" }}>
                      {["Date", "Reference", "Description", "Debit", "Credit", "Balance"].map((h) => (
                        <th key={h} style={{ padding: isMobile ? "6px 8px" : "9px 12px", textAlign: ["Debit","Credit","Balance"].includes(h) ? "right" : "left",
                          fontWeight: 700, fontSize: 11, textTransform: "uppercase", color: "#334155" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {ledger.data.entries.map((e, i) => (
                      <tr key={i} style={{ background: i % 2 === 0 ? "#fff" : "#f8fafc", borderBottom: "1px solid #e2e8f0" }}>
                        <td style={{ padding: isMobile ? "5px 8px" : "7px 12px" }}>{e.date}</td>
                        <td style={{ padding: isMobile ? "5px 8px" : "7px 12px", fontFamily: "monospace", fontSize: 11 }}>{e.ref_id}</td>
                        <td style={{ padding: isMobile ? "5px 8px" : "7px 12px", color: "#475569" }}>{e.description || e.memo || "—"}</td>
                        <td style={{ padding: isMobile ? "5px 8px" : "7px 12px", textAlign: "right", fontFamily: "monospace", color: e.debit > 0 ? "#1e293b" : "#94a3b8" }}>
                          {e.debit > 0 ? fmt(e.debit) : "—"}
                        </td>
                        <td style={{ padding: isMobile ? "5px 8px" : "7px 12px", textAlign: "right", fontFamily: "monospace", color: e.credit > 0 ? "#1e293b" : "#94a3b8" }}>
                          {e.credit > 0 ? fmt(e.credit) : "—"}
                        </td>
                        <td style={{ padding: isMobile ? "5px 8px" : "7px 12px", textAlign: "right", fontFamily: "monospace", fontWeight: 700,
                          color: e.balance >= 0 ? "#1e293b" : ACCENT.expense }}>
                          {fmt(e.balance)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Section>
    );
  }

  return (
    <Section
      title="Chart of Accounts"
      right={
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setShowCreate(!showCreate)} style={shellStyles.primaryButton(isMobile)}>
            {showCreate ? "Cancel" : "+ Add Account"}
          </button>
          <button onClick={handleSeed} disabled={seeding} style={shellStyles.smallButton(isMobile)}>
            {seeding ? "Seeding..." : "Seed Defaults"}
          </button>
        </div>
      }
    >
      {/* Create form */}
      {showCreate && (
        <div style={{ marginBottom: 20, padding: 16, background: "#f0f7ff", border: "1px solid #bfdbfe", borderRadius: 8,
          display: "grid", gap: 10, gridTemplateColumns: isMobile ? "1fr" : "repeat(3,1fr)" }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 4 }}>CODE *</div>
            <input value={newAcct.code} onChange={(e) => setNewAcct({ ...newAcct, code: e.target.value })}
              placeholder="e.g. 6700" style={{ ...shellStyles.searchInput, padding: "7px 10px" }} />
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 4 }}>NAME *</div>
            <input value={newAcct.name} onChange={(e) => setNewAcct({ ...newAcct, name: e.target.value })}
              placeholder="e.g. Insurance" style={{ ...shellStyles.searchInput, padding: "7px 10px" }} />
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 4 }}>TYPE *</div>
            <select value={newAcct.account_type} onChange={(e) => setNewAcct({ ...newAcct, account_type: e.target.value })}
              style={{ ...shellStyles.searchInput, padding: "7px 10px" }}>
              {["ASSET","LIABILITY","EQUITY","REVENUE","COGS","EXPENSE"].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div style={{ gridColumn: isMobile ? "1" : "1 / -1" }}>
            <button onClick={handleCreate} disabled={creating} style={{ ...shellStyles.primaryButton(isMobile), minHeight: 36, padding: "0 20px" }}>
              {creating ? "Creating..." : "Create Account"}
            </button>
          </div>
        </div>
      )}

      {/* Type filter */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
        {TYPE_OPTIONS.map((t) => (
          <button key={t} onClick={() => setFilter(t)}
            style={{ padding: "4px 12px", borderRadius: 16, border: "1px solid",
              fontSize: 11, fontWeight: 700, cursor: "pointer",
              background: filter === t ? (typeColor(t) || "#1b6cff") : "#f8fafc",
              color: filter === t ? "#fff" : "#475569",
              borderColor: filter === t ? (typeColor(t) || "#1b6cff") : "#cbd5e1" }}>
            {t}
          </button>
        ))}
      </div>

      {loading && <EmptyState text="Loading accounts..." />}
      {error   && <EmptyState text={`Error: ${error}`} />}
      {!loading && !error && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: isMobile ? 11 : 13 }}>
            <thead>
              <tr style={{ background: "#edf4ff", borderBottom: "2px solid #bfdbfe" }}>
                {["Code", "Name", "Type", "Normal Balance", ""].map((h) => (
                  <th key={h} style={{ padding: isMobile ? "6px 8px" : "9px 12px", textAlign: "left",
                    fontWeight: 700, fontSize: 11, textTransform: "uppercase", color: "#334155" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((acc, i) => (
                <tr key={acc.id} style={{ background: i % 2 === 0 ? "#fff" : "#f8fafc", borderBottom: "1px solid #e2e8f0" }}>
                  <td style={{ padding: isMobile ? "5px 8px" : "7px 12px", fontFamily: "monospace", fontWeight: 700 }}>{acc.code}</td>
                  <td style={{ padding: isMobile ? "5px 8px" : "7px 12px" }}>
                    {acc.name}
                    {acc.is_system && <span style={{ marginLeft: 6, fontSize: 10, color: "#94a3b8" }}>system</span>}
                  </td>
                  <td style={{ padding: isMobile ? "5px 8px" : "7px 12px" }}>{pill(typeColor(acc.account_type), acc.account_type)}</td>
                  <td style={{ padding: isMobile ? "5px 8px" : "7px 12px", color: "#64748b", fontSize: 12 }}>{acc.normal_balance}</td>
                  <td style={{ padding: isMobile ? "5px 8px" : "7px 12px" }}>
                    <button onClick={() => openLedger(acc)} style={{ ...shellStyles.smallButton(isMobile), padding: "2px 10px", minHeight: 26, fontSize: 11 }}>
                      View Ledger
                    </button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={5} style={{ padding: 20, textAlign: "center", color: "#94a3b8" }}>No accounts found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

// ── JOURNAL VIEW ──────────────────────────────────────────────────────────────

function JournalView() {
  const [isMobile] = useMobile();
  const [range, setRange]   = useState({ from: firstOfMonth(), to: today() });
  const [refType, setRefType] = useState("");
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      setEntries(await accountingAPI.journal({
        date_from: range.from, date_to: range.to,
        ref_type: refType || undefined,
      }));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [range.from, range.to, refType]);

  useEffect(() => { load(); }, [load]);

  const refTypeColor = (t) => ({ transaction: ACCENT.revenue, grn: ACCENT.asset, void: ACCENT.expense, manual: ACCENT.neutral }[t] || ACCENT.neutral);

  return (
    <Section
      title="Journal Entries"
      right={
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <DateRange from={range.from} to={range.to} onChange={setRange} />
          <select value={refType} onChange={(e) => setRefType(e.target.value)}
            style={{ ...shellStyles.searchInput, width: 130, padding: "6px 10px", fontSize: 12 }}>
            <option value="">All types</option>
            <option value="transaction">Sales</option>
            <option value="grn">GRN</option>
            <option value="void">Voids</option>
            <option value="manual">Manual</option>
          </select>
        </div>
      }
    >
      {loading && <EmptyState text="Loading journal..." />}
      {error   && <EmptyState text={`Error: ${error}`} />}
      {!loading && !error && entries.length === 0 && <EmptyState text="No journal entries in this period." />}
      {!loading && entries.map((entry) => (
        <div key={entry.id} style={{ marginBottom: 8, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
          {/* Entry header */}
          <div
            onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: isMobile ? "8px 12px" : "10px 16px", cursor: "pointer",
              background: expanded === entry.id ? "#f0f7ff" : "#f8fafc",
              borderBottom: expanded === entry.id ? "1px solid #bfdbfe" : "none" }}>
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 700, color: "#334155" }}>{entry.ref_id}</span>
              {pill(refTypeColor(entry.ref_type), entry.ref_type)}
              <span style={{ fontSize: 12, color: "#64748b" }}>{entry.description}</span>
            </div>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <span style={{ fontSize: 12, color: "#64748b" }}>{entry.entry_date}</span>
              <span style={{ fontSize: 11 }}>{expanded === entry.id ? "▲" : "▼"}</span>
            </div>
          </div>

          {/* Lines — shown when expanded */}
          {expanded === entry.id && (
            <div style={{ padding: isMobile ? "8px 12px" : "12px 16px" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #e2e8f0" }}>
                    {["Account", "Memo", "Debit", "Credit"].map((h) => (
                      <th key={h} style={{ padding: "4px 8px", textAlign: ["Debit","Credit"].includes(h) ? "right" : "left",
                        fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#64748b" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {entry.lines.map((line, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "5px 8px" }}>
                        <span style={{ fontFamily: "monospace", fontSize: 11, marginRight: 6 }}>{line.account_code}</span>
                        {line.account_name}
                      </td>
                      <td style={{ padding: "5px 8px", color: "#64748b" }}>{line.memo || "—"}</td>
                      <td style={{ padding: "5px 8px", textAlign: "right", fontFamily: "monospace", color: line.debit > 0 ? "#1e293b" : "#94a3b8" }}>
                        {line.debit > 0 ? fmt(line.debit) : "—"}
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right", fontFamily: "monospace", color: line.credit > 0 ? "#1e293b" : "#94a3b8" }}>
                        {line.credit > 0 ? fmt(line.credit) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ marginTop: 8, textAlign: "right", fontSize: 11, color: entry.is_balanced ? ACCENT.revenue : ACCENT.expense, fontWeight: 700 }}>
                {entry.is_balanced ? "✓ Balanced" : "⚠ Unbalanced"}
              </div>
            </div>
          )}
        </div>
      ))}
    </Section>
  );
}

// ── ROOT COMPONENT ────────────────────────────────────────────────────────────

// Group tabs by category so the nav bar stays scannable
const SUB_TAB_GROUPS = [
  {
    label: "Statements",
    tabs: [
      { key: "pl",       label: "P&L" },
      { key: "balance",  label: "Balance Sheet" },
      { key: "vat",      label: "VAT" },
      { key: "trial",    label: "Trial Balance" },
    ],
  },
  {
    label: "Ledger",
    tabs: [
      { key: "accounts", label: "Accounts" },
      { key: "journal",  label: "Journal" },
    ],
  },
  {
    label: "Aging & Statements",
    tabs: [
      { key: "ap_aging",           label: "AP Aging" },
      { key: "ar_aging",           label: "AR Aging" },
      { key: "supplier_statement", label: "Supplier Stmt" },
      { key: "customer_statement", label: "Customer Stmt" },
    ],
  },
  {
    label: "Multi-Branch",
    tabs: [
      { key: "consolidated_pl",   label: "Consolidated P&L" },
      { key: "branch_comparison", label: "Branch Comparison" },
    ],
  },
];

const ALL_SUB_TABS = SUB_TAB_GROUPS.flatMap((g) => g.tabs);

export default function AccountingTab() {
  const [isMobile] = useMobile();
  const [view, setView] = useState("pl");

  return (
    <div style={{ display: "grid", gap: isMobile ? 12 : 16 }}>
      {/* Grouped sub-tab navigation */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {SUB_TAB_GROUPS.map((group) => (
          <div key={group.label} style={{ display: "flex", gap: isMobile ? 4 : 6, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: ".08em", minWidth: isMobile ? 0 : 110 }}>
              {group.label}
            </span>
            {group.tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setView(t.key)}
                style={shellStyles.tabButton(view === t.key, isMobile)}
              >
                {t.label}
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* Active view */}
      {view === "pl"                 && <PLView />}
      {view === "balance"            && <BalanceSheetView />}
      {view === "vat"                && <VATView />}
      {view === "trial"              && <TrialBalanceView />}
      {view === "accounts"           && <AccountsView />}
      {view === "journal"            && <JournalView />}
      {view === "ap_aging"           && <APAgingView />}
      {view === "ar_aging"           && <ARAgingView />}
      {view === "supplier_statement" && <SupplierStatementView />}
      {view === "customer_statement" && <CustomerStatementView />}
      {view === "consolidated_pl"    && <ConsolidatedPLView />}
      {view === "branch_comparison"  && <BranchComparisonView />}
    </div>
  );
}
