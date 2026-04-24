/**
 * CashSessionsTab — Cash Sessions management module for BackOffice.
 *
 * Displays:
 *   List — All cash sessions with status, variance, and timestamps
 *   Detail — Full session information (opened_at, closed_at, variance, counted_cash, etc.)
 *
 * Role rules:
 *   CASHIER    — can view their own sessions
 *   SUPERVISOR+ — can view all sessions and reopen if needed
 */

import { useState, useEffect } from "react";
import { cashSessionsAPI, fmtKES } from "../../api/client";
import { Section, EmptyState } from "./UIComponents";
import { shellStyles } from "./styles";

const STATUS_COLORS = {
  open:   { bg: "#dbeafe", text: "#1e40af", border: "#93c5fd" },
  closed: { bg: "#d1fae5", text: "#065f46", border: "#6ee7b7" },
};

export default function CashSessionsTab() {
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    try {
      setLoading(true);
      setError("");
      const response = await cashSessionsAPI.list();
      setSessions(Array.isArray(response) ? response : response.items || []);
    } catch (err) {
      setError(err.message || "Failed to load cash sessions");
    } finally {
      setLoading(false);
    }
  };

  if (selectedSession) {
    return (
      <div style={{ display: "grid", gap: 16 }}>
        <button
          onClick={() => setSelectedSession(null)}
          style={shellStyles.secondaryButton}
        >
          ← Back to List
        </button>
        <SessionDetail session={selectedSession} />
      </div>
    );
  }

  return (
    <Section title="Cash Sessions" icon="💰">
      {error && (
        <div style={{ padding: 12, background: "#fee2e2", color: "#7f1d1d", borderRadius: 4 }}>
          {error}
        </div>
      )}
      {loading ? (
        <div>Loading cash sessions...</div>
      ) : sessions.length === 0 ? (
        <EmptyState text="No cash sessions found" />
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: 13,
          }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #e5e7eb" }}>
                <th style={{ padding: 10, textAlign: "left" }}>Session #</th>
                <th style={{ padding: 10, textAlign: "left" }}>Cashier ID</th>
                <th style={{ padding: 10, textAlign: "left" }}>Status</th>
                <th style={{ padding: 10, textAlign: "right" }}>Opening Float</th>
                <th style={{ padding: 10, textAlign: "right" }}>Counted Cash</th>
                <th style={{ padding: 10, textAlign: "right" }}>Variance</th>
                <th style={{ padding: 10, textAlign: "left" }}>Opened</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session) => {
                const status = session.status || "open";
                const colors = STATUS_COLORS[status] || STATUS_COLORS.open;
                const variance = session.variance ? parseFloat(session.variance) : 0;
                const varianceColor = variance > 0 ? "#059669" : variance < 0 ? "#dc2626" : "#6b7280";

                return (
                  <tr
                    key={session.id}
                    style={{
                      borderBottom: "1px solid #f3f4f6",
                      cursor: "pointer",
                      "&:hover": { background: "#f9fafb" },
                    }}
                    onClick={() => setSelectedSession(session)}
                  >
                    <td style={{ padding: 10, fontWeight: 500 }}>{session.session_number}</td>
                    <td style={{ padding: 10 }}>{session.cashier_id}</td>
                    <td style={{ padding: 10 }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "4px 8px",
                          background: colors.bg,
                          color: colors.text,
                          borderRadius: 4,
                          fontSize: 12,
                          fontWeight: 500,
                          textTransform: "capitalize",
                        }}
                      >
                        {status}
                      </span>
                    </td>
                    <td style={{ padding: 10, textAlign: "right" }}>
                      {fmtKES(session.opening_float)}
                    </td>
                    <td style={{ padding: 10, textAlign: "right" }}>
                      {session.counted_cash ? fmtKES(session.counted_cash) : "-"}
                    </td>
                    <td style={{ padding: 10, textAlign: "right", color: varianceColor, fontWeight: 500 }}>
                      {variance > 0 ? "+" : ""}{fmtKES(variance)}
                    </td>
                    <td style={{ padding: 10, fontSize: 11 }}>
                      {session.opened_at ? new Date(session.opened_at).toLocaleString() : "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function SessionDetail({ session }) {
  return (
    <Section title={`Session ${session.session_number}`} icon="📋">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 16 }}>
        <Field label="Session Number" value={session.session_number} />
        <Field label="Status" value={session.status?.toUpperCase()} />
        <Field label="Cashier ID" value={session.cashier_id} />
        <Field label="Terminal ID" value={session.terminal_id || "-"} />
        <Field label="Opening Float" value={fmtKES(session.opening_float)} />
        <Field label="Expected Cash" value={fmtKES(session.expected_cash || 0)} />
        <Field label="Counted Cash" value={session.counted_cash ? fmtKES(session.counted_cash) : "-"} />
        <Field
          label="Variance"
          value={session.variance ? fmtKES(session.variance) : "-"}
          style={{ color: session.variance > 0 ? "#059669" : session.variance < 0 ? "#dc2626" : "#6b7280" }}
        />
        <Field label="Opened At" value={session.opened_at ? new Date(session.opened_at).toLocaleString() : "-"} />
        <Field label="Closed At" value={session.closed_at ? new Date(session.closed_at).toLocaleString() : "-"} />
        <Field label="Opened By" value={session.opened_by} />
        <Field label="Closed By" value={session.closed_by || "-"} />
      </div>
      {session.notes && (
        <div style={{ marginTop: 16, padding: 12, background: "#f9fafb", borderRadius: 4 }}>
          <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8 }}>Notes</div>
          <div style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{session.notes}</div>
        </div>
      )}
    </Section>
  );
}

function Field({ label, value, style }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, opacity: 0.7, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 13, fontWeight: 500, ...style }}>
        {value || "-"}
      </div>
    </div>
  );
}
