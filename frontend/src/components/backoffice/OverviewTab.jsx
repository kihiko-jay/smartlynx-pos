import { useState, useEffect } from "react";
import {
  transactionsAPI,
  reportsAPI,
  fmtKES,
} from "../../api/client";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { KPIBox, Section, EmptyState, TableShell } from "./UIComponents";

export default function OverviewTab() {
  const [summary, setSummary] = useState(null);
  const [weekly, setWeekly] = useState(null);
  const [topProds, setTopProds] = useState([]);
  const [txns, setTxns] = useState([]);
  const [lowStock, setLowStock] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    Promise.all([
      transactionsAPI.todaySummary(),
      reportsAPI.weekly(),
      reportsAPI.topProducts(),
      transactionsAPI.list({ limit: 8 }),
      reportsAPI.lowStock(),
    ])
      .then(([s, w, tp, t, ls]) => {
        setSummary(s);
        setWeekly(w);
        setTopProds(tp.products || []);
        setTxns(t || []);
        setLowStock(ls.items || []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <EmptyState text="Loading dashboard..." />;

  const days = weekly?.daily_breakdown || [];
  const byMethod = summary?.by_payment_method || {};
  const totalByMethod = Object.values(byMethod).reduce((s, v) => s + v, 0) || 1;
  const todaySales = days[6]?.total_sales || 0;
  const yesterdaySales = days[5]?.total_sales || 0;
  const todayTxns = days[6]?.transaction_count || 0;
  const yesterdayTxns = days[5]?.transaction_count || 0;

  const calcDelta = (today, yesterday) => {
    if (!yesterday) return null;
    const pct = Math.round(((today - yesterday) / yesterday) * 100);
    return `${pct >= 0 ? "+" : ""}${pct}% vs yday`;
  };

  return (
    <div style={{ display: "grid", gap: isMobile ? 12 : 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(2, minmax(0,1fr))" : "repeat(4, minmax(0,1fr))", gap: isMobile ? 8 : 12 }}>
        <KPIBox
          label="Today's Sales"
          value={fmtKES(summary?.total_sales || 0)}
          sub="all tills"
          accent="#155eef"
          delta={calcDelta(todaySales, yesterdaySales)}
        />
        <KPIBox
          label="Transactions"
          value={summary?.transaction_count || 0}
          sub="completed today"
          accent="#15803d"
          delta={calcDelta(todayTxns, yesterdayTxns)}
        />
        {!isMobile && (
          <>
            <KPIBox
              label="Avg Basket"
              value={fmtKES(
                summary?.transaction_count
                  ? Math.round(
                      (summary?.total_sales || 0) / summary.transaction_count
                    )
                  : 0
              )}
              sub="per transaction"
              accent="#d97706"
            />
            <KPIBox
              label="Low Stock"
              value={lowStock.length}
              sub="needs reorder"
              accent="#b42318"
            />
          </>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1.6fr 1fr", gap: isMobile ? 12 : 16 }}>
        <Section title="Weekly Sales Overview">
          <ResponsiveContainer width="100%" height={isMobile ? 180 : 220}>
            <BarChart data={days} barSize={isMobile ? 20 : 34}>
              <XAxis
                dataKey="day"
                tick={{ fontSize: isMobile ? 9 : 11, fill: "#64748b" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis hide />
              <Tooltip formatter={(v) => [fmtKES(v), "Sales"]} />
              <Bar dataKey="total_sales" radius={[6, 6, 0, 0]}>
                {days.map((_, i) => (
                  <Cell
                    key={i}
                    fill={i === days.length - 1 ? "#155eef" : "#9ec5fe"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Section>

        <Section title="Payment Mix">
          <div style={{ display: "grid", gap: isMobile ? 10 : 14 }}>
            {Object.entries(byMethod).map(([method, amount]) => {
              const pct = Math.round((amount / totalByMethod) * 100);
              const color =
                method === "mpesa"
                  ? "#16a34a"
                  : method === "cash"
                  ? "#d97706"
                  : "#155eef";
              return (
                <div key={method}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginBottom: 6,
                      fontSize: isMobile ? 11 : 12,
                      fontWeight: 700,
                    }}
                  >
                    <span style={{ textTransform: "uppercase" }}>{method}</span>
                    <span>
                      {pct}% · {fmtKES(amount)}
                    </span>
                  </div>
                  <div
                    style={{
                      height: 10,
                      background: "#e5edf9",
                      borderRadius: 999,
                    }}
                  >
                    <div
                      style={{
                        width: `${pct}%`,
                        height: "100%",
                        background: color,
                        borderRadius: 999,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1.2fr 1fr", gap: isMobile ? 12 : 16 }}>
        <Section title="Top Products Today">
          <TableShell headers={["Product", "SKU", "Units Sold", "Revenue"]} hideColumns={isMobile ? [1] : []}>
            {(topProds || []).slice(0, 8).map((p, idx) => {
              const displayCols = isMobile ? ["Product", "Units Sold", "Revenue"] : ["Product", "SKU", "Units Sold", "Revenue"];
              return (
                <div
                  key={p.product_id || idx}
                  style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${displayCols.length}, minmax(0,1fr))`,
                    borderTop: idx ? "1px solid #e2e8f0" : "none",
                    background: idx % 2 ? "#f8fbff" : "#fff",
                  }}
                >
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontWeight: 600, fontSize: isMobile ? 11 : 12 }}>
                    {isMobile ? p.product_name.substring(0, 20) : p.product_name}
                  </div>
                  {!isMobile && <div style={{ padding: "10px 12px", color: "#64748b" }}>
                    {p.sku}
                  </div>}
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: isMobile ? 11 : 12 }}>{p.units_sold}</div>
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", color: "#155eef", fontWeight: 700, fontSize: isMobile ? 11 : 12 }}>
                    {fmtKES(p.revenue)}
                  </div>
                </div>
              );
            })}
          </TableShell>
        </Section>

        <Section title={`Low Stock Alerts (${lowStock.length})`}>
          <div style={{ display: "grid", gap: isMobile ? 8 : 10 }}>
            {lowStock.length === 0 ? (
              <EmptyState text="No low stock items." />
            ) : (
              lowStock.slice(0, 8).map((p, idx) => (
                <div
                  key={p.product_id || idx}
                  style={{
                    background:
                      p.status === "CRITICAL" ? "#fef2f2" : "#fff7ed",
                    border: `1px solid ${
                      p.status === "CRITICAL" ? "#fecaca" : "#fdba74"
                    }`,
                    borderRadius: 8,
                    padding: isMobile ? 10 : 12,
                  }}
                >
                  <div style={{ fontWeight: 700, fontSize: isMobile ? 11 : 12 }}>{isMobile ? p.name.substring(0, 20) : p.name}</div>
                  <div style={{ fontSize: isMobile ? 10 : 12, color: "#64748b", marginTop: 4 }}>
                    {p.sku}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginTop: 8,
                      fontSize: isMobile ? 10 : 12,
                      gap: 4,
                    }}
                  >
                    <span
                      style={{
                        color:
                          p.status === "CRITICAL" ? "#b42318" : "#c2410c",
                        fontWeight: 700,
                      }}
                    >
                      {p.status === "CRITICAL"
                        ? "Out of stock"
                        : `${p.current_stock} left`}
                    </span>
                    <span style={{ color: "#64748b" }}>min {p.reorder_level}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </Section>
      </div>

      <Section title="Recent Transactions">
        <TableShell headers={["TXN #", "Total", "Payment", "Status", "Date"]} hideColumns={isMobile ? [3, 4] : []}>
          {(txns || []).slice(0, 8).map((t, idx) => {
            const displayCols = isMobile ? ["TXN #", "Total", "Payment"] : ["TXN #", "Total", "Payment", "Status", "Date"];
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
                <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontWeight: 700, color: "#155eef", fontSize: isMobile ? 11 : 12 }}>
                  {t.txn_number}
                </div>
                <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: isMobile ? 11 : 12 }}>{fmtKES(t.total)}</div>
                <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", textTransform: "uppercase", fontSize: isMobile ? 10 : 12 }}>
                  {t.payment_method}
                </div>
                {!isMobile && (
                  <>
                    <div style={{ padding: "10px 12px", fontSize: 12 }}>{t.status}</div>
                    <div style={{ padding: "10px 12px", color: "#64748b", fontSize: 12 }}>
                      {new Date(t.created_at).toLocaleString("en-KE", {
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </TableShell>
      </Section>
    </div>
  );
}
