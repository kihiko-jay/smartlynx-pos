import { useState, useEffect, useCallback } from "react";
import { platformAPI } from "../../api/client";
import { C, FONT_MONO, PLAN_COLOR, STATUS_COLOR } from "./styles";
import { Badge, Pill, Btn, Select, Alert, Spinner } from "./UIComponents";

const td = {
  padding: "12px 14px",
  fontSize: 12,
  color: C.text,
  verticalAlign: "middle",
};

export default function PaymentsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    const params = filter ? { status: filter } : {};
    platformAPI
      .payments(params)
      .then(setData)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const totalConfirmed = (data?.payments || [])
    .filter((p) => p.status === "confirmed")
    .reduce((s, p) => s + parseFloat(p.amount || 0), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <Select value={filter} onChange={setFilter}>
          <option value="">All payments</option>
          <option value="confirmed">Confirmed</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
        </Select>
        <Btn variant="ghost" small onClick={load}>
          Refresh
        </Btn>
        {totalConfirmed > 0 && (
          <Pill
            label={`KES ${totalConfirmed.toLocaleString("en-KE")} confirmed`}
          />
        )}
      </div>

      {err && <Alert type="error" msg={err} />}

      {loading ? (
        <Spinner />
      ) : (
        <div
          style={{
            background: C.card,
            border: `1px solid ${C.border}`,
            borderRadius: 10,
            overflow: "hidden",
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                {["#", "Store", "Plan", "Amount", "Months", "M-PESA Ref", "Status", "Date"].map(
                  (h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: "left",
                        fontSize: 10,
                        color: C.muted,
                        fontFamily: FONT_MONO,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        padding: "12px 14px",
                      }}
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {(data?.payments || []).map((p, i) => (
                <tr
                  key={p.payment_id}
                  style={{
                    borderBottom: `1px solid ${C.border}22`,
                    background: i % 2 === 0 ? "transparent" : C.surface + "44",
                  }}
                >
                  <td style={td}>{p.payment_id}</td>
                  <td style={td}>
                    <div
                      style={{
                        fontSize: 12,
                        color: C.text,
                        fontFamily: FONT_MONO,
                      }}
                    >
                      {p.store_name || `Store #${p.store_id}`}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: C.muted,
                        fontFamily: FONT_MONO,
                      }}
                    >
                      #{p.store_id}
                    </div>
                  </td>
                  <td style={td}>
                    <Badge label={p.plan} color={PLAN_COLOR[p.plan]} />
                  </td>
                  <td
                    style={{
                      ...td,
                      color: C.green,
                      fontFamily: FONT_MONO,
                      fontWeight: 600,
                    }}
                  >
                    KES {parseFloat(p.amount).toLocaleString("en-KE")}
                  </td>
                  <td style={td}>{p.months}</td>
                  <td
                    style={{
                      ...td,
                      fontFamily: FONT_MONO,
                      fontSize: 11,
                      color: C.muted,
                    }}
                  >
                    {p.mpesa_ref || "—"}
                  </td>
                  <td style={td}>
                    <Badge
                      label={p.status}
                      color={
                        p.status === "confirmed"
                          ? STATUS_COLOR.active
                          : p.status === "pending"
                          ? STATUS_COLOR.trialing
                          : STATUS_COLOR.cancelled
                      }
                    />
                  </td>
                  <td
                    style={{
                      ...td,
                      fontSize: 11,
                      color: C.muted,
                      fontFamily: FONT_MONO,
                    }}
                  >
                    {p.created_at
                      ? new Date(p.created_at).toLocaleDateString("en-KE")
                      : "—"}
                  </td>
                </tr>
              ))}
              {data?.payments?.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    style={{
                      textAlign: "center",
                      padding: "30px 0",
                      color: C.muted,
                      fontFamily: FONT_MONO,
                      fontSize: 12,
                    }}
                  >
                    No payments found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
