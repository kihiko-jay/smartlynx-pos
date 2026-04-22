import { useState, useEffect } from "react";
import { platformAPI } from "../../api/client";
import { C, FONT_DISPLAY, FONT_MONO, PLAN_COLOR, STATUS_COLOR } from "./styles";
import { StatCard, SectionHead, Alert, Badge, Spinner } from "./UIComponents";

export default function OverviewTab() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    platformAPI
      .metrics()
      .then(setMetrics)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;
  if (err) return <Alert type="error" msg={`Failed to load metrics: ${err}`} />;
  if (!metrics) return null;

  // Aggregate plan counts from metrics
  const byPlan = {};
  (metrics.stores_by_plan || []).forEach((r) => {
    byPlan[r.plan] = (byPlan[r.plan] || 0) + r.count;
  });
  const totalStores = Object.values(byPlan).reduce((a, b) => a + b, 0);
  const activeCount = (metrics.stores_by_plan || [])
    .filter((r) => r.status === "active")
    .reduce((a, r) => a + r.count, 0);

  const mrr = metrics.total_revenue_kes || 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Alerts row */}
      {metrics.trials_expiring_soon > 0 && (
        <Alert
          type="warn"
          msg={`⚠ ${metrics.trials_expiring_soon} trial${
            metrics.trials_expiring_soon > 1 ? "s" : ""
          } expiring within 3 days — follow up to convert`}
        />
      )}
      {metrics.expired_trials > 0 && (
        <Alert
          type="warn"
          msg={`⚠ ${metrics.expired_trials} expired trial${
            metrics.expired_trials > 1 ? "s" : ""
          } — these stores cannot access premium features`}
        />
      )}

      {/* Metric cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: 12,
        }}
      >
        <StatCard label="Total Stores" value={totalStores} accent={C.accent} />
        <StatCard
          label="Active Subs"
          value={activeCount}
          accent={C.green}
          sub="paying customers"
        />
        <StatCard
          label="Revenue (Total)"
          value={`KES ${mrr.toLocaleString("en-KE")}`}
          accent={C.amber}
          sub="all confirmed payments"
        />
        <StatCard
          label="Payments"
          value={metrics.total_confirmed_payments || 0}
          accent={C.purple}
          sub="confirmed M-PESA"
        />
      </div>

      {/* Plan breakdown */}
      <div
        style={{
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: 10,
          padding: "20px 22px",
        }}
      >
        <SectionHead title="Stores by plan" />
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: 10,
          }}
        >
          {["free", "starter", "growth", "pro"].map((plan) => {
            const count = byPlan[plan] || 0;
            const pc = PLAN_COLOR[plan] || { fg: C.muted, bg: C.dim };
            return (
              <div
                key={plan}
                style={{
                  background: pc.bg,
                  border: `1px solid ${pc.fg}33`,
                  borderRadius: 8,
                  padding: "14px 16px",
                }}
              >
                <div
                  style={{
                    fontSize: 10,
                    color: pc.fg,
                    fontFamily: FONT_MONO,
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                    marginBottom: 8,
                  }}
                >
                  {plan}
                </div>
                <div
                  style={{
                    fontSize: 26,
                    fontWeight: 700,
                    color: pc.fg,
                    fontFamily: FONT_DISPLAY,
                  }}
                >
                  {count}
                </div>
                <div
                  style={{
                    fontSize: 10,
                    color: pc.fg + "99",
                    marginTop: 4,
                    fontFamily: FONT_MONO,
                  }}
                >
                  store{count !== 1 ? "s" : ""}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Status breakdown table */}
      <div
        style={{
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: 10,
          padding: "20px 22px",
        }}
      >
        <SectionHead title="Subscription status breakdown" />
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Plan", "Status", "Count"].map((h) => (
                <th
                  key={h}
                  style={{
                    textAlign: "left",
                    fontSize: 10,
                    color: C.muted,
                    fontFamily: FONT_MONO,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    padding: "6px 0",
                    borderBottom: `1px solid ${C.border}`,
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(metrics.stores_by_plan || []).map((r, i) => (
              <tr key={i} style={{ borderBottom: `1px solid ${C.border}22` }}>
                <td style={{ padding: "10px 0" }}>
                  <Badge label={r.plan} color={PLAN_COLOR[r.plan]} />
                </td>
                <td style={{ padding: "10px 0" }}>
                  <Badge label={r.status} color={STATUS_COLOR[r.status]} />
                </td>
                <td
                  style={{
                    padding: "10px 0",
                    color: C.text,
                    fontFamily: FONT_MONO,
                    fontSize: 13,
                  }}
                >
                  {r.count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
