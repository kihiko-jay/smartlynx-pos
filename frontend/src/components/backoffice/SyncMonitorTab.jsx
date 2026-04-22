import { useState, useEffect } from "react";
import { auditAPI } from "../../api/client";
import { shellStyles } from "./styles";
import { Section, EmptyState, TableShell } from "./UIComponents";

export default function SyncMonitorTab() {
  const [syncLog, setSyncLog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    auditAPI
      .syncLog({ limit: 100 })
      .then((d) => setSyncLog(d?.entries || []))
      .finally(() => setLoading(false));
  }, []);

  const filtered =
    filter === "all"
      ? syncLog
      : syncLog.filter((e) => e.status === filter);

  return (
    <div style={{ display: "grid", gap: isMobile ? 12 : 16 }}>
      <Section
        title="Sync Monitor"
        right={
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "auto auto auto auto", gap: isMobile ? 4 : 8 }}>
            {["all", "success", "error", "conflict"].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={
                  filter === f
                    ? shellStyles.primaryButton(isMobile)
                    : shellStyles.smallButton(isMobile)
                }
              >
                {f}
              </button>
            ))}
          </div>
        }
      >
        {loading ? (
          <EmptyState text="Loading sync log..." />
        ) : (
          <TableShell
            headers={[
              "Entity",
              "Direction",
              "Status",
              "In",
              "Out",
              "Duration",
              "Checkpoint",
              "Time",
            ]}
            hideColumns={isMobile ? [3, 4, 5, 6, 7] : []}
          >
            {filtered.map((e, idx) => {
              const displayCols = isMobile ? ["Entity", "Direction", "Status"] : ["Entity", "Direction", "Status", "In", "Out", "Duration", "Checkpoint", "Time"];
              return (
                <div
                  key={e.id || idx}
                  style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${displayCols.length}, minmax(0,1fr))`,
                    borderTop: idx ? "1px solid #e2e8f0" : "none",
                    background: idx % 2 ? "#f8fbff" : "#fff",
                  }}
                >
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontWeight: 700, fontSize: isMobile ? 11 : 12 }}>
                    {e.entity}
                  </div>
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: isMobile ? 11 : 12 }}>{e.direction}</div>
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: isMobile ? 11 : 12 }}>{e.status}</div>
                  {!isMobile && (
                    <>
                      <div style={{ padding: "10px 12px", fontSize: 12 }}>{e.records_in}</div>
                      <div style={{ padding: "10px 12px", fontSize: 12 }}>{e.records_out}</div>
                      <div style={{ padding: "10px 12px", fontSize: 12 }}>
                        {e.duration_ms ? `${e.duration_ms}ms` : "—"}
                      </div>
                      <div style={{ padding: "10px 12px", color: "#64748b", fontSize: 12 }}>
                        {e.checkpoint
                          ? new Date(e.checkpoint).toLocaleString("en-KE", {
                              dateStyle: "short",
                              timeStyle: "short",
                            })
                          : "—"}
                      </div>
                      <div style={{ padding: "10px 12px", color: "#64748b", fontSize: 12 }}>
                        {new Date(e.synced_at).toLocaleString("en-KE", {
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
        )}
      </Section>
    </div>
  );
}
