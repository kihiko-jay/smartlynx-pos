import { useState, useEffect } from "react";
import { auditAPI } from "../../api/client";
import { shellStyles } from "./styles";
import { Section, EmptyState, TableShell } from "./UIComponents";

export default function AuditTrailTab() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [entity, setEntity] = useState("all");
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    const params = entity !== "all" ? { entity } : {};
    auditAPI
      .trail({ limit: 100, ...params })
      .then((d) => setEntries(d?.entries || []))
      .finally(() => setLoading(false));
  }, [entity]);

  return (
    <Section
      title="Audit Trail"
      right={
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "auto auto auto auto", gap: isMobile ? 4 : 8 }}>
          {["all", "transaction", "product", "employee"].map((e) => (
            <button
              key={e}
              onClick={() => setEntity(e)}
              style={
                entity === e
                  ? shellStyles.primaryButton(isMobile)
                  : shellStyles.smallButton(isMobile)
              }
            >
              {isMobile ? e.split("")[0].toUpperCase() : e}
            </button>
          ))}
        </div>
      }
    >
      {loading ? (
        <EmptyState text="Loading audit trail..." />
      ) : (
        <TableShell
          headers={["Actor", "Action", "Entity", "Entity ID", "Before / After", "Time"]}
          hideColumns={isMobile ? [3, 4, 5] : []}
        >
          {entries.map((e, idx) => {
            const displayCols = isMobile ? ["Actor", "Action", "Entity"] : ["Actor", "Action", "Entity", "Entity ID", "Before / After", "Time"];
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
                  {e.actor || "system"}
                </div>
                <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: isMobile ? 11 : 12 }}>{e.action}</div>
                <div
                  style={{
                    padding: isMobile ? "8px 10px" : "10px 12px",
                    textTransform: "uppercase",
                    fontSize: isMobile ? 10 : 12,
                  }}
                >
                  {e.entity}
                </div>
                {!isMobile && (
                  <>
                    <div style={{ padding: "10px 12px", color: "#155eef", fontSize: 12 }}>
                      {e.entity_id}
                    </div>
                    <div style={{ padding: "10px 12px", color: "#64748b", fontSize: 11 }}>
                      {e.before ? (
                        <span style={{ color: "#b42318" }}>
                          {JSON.stringify(e.before).slice(0, 60)}
                        </span>
                      ) : null}
                      {e.before && e.after ? " → " : null}
                      {e.after ? (
                        <span style={{ color: "#15803d" }}>
                          {JSON.stringify(e.after).slice(0, 60)}
                        </span>
                      ) : null}
                      {e.notes ? <div style={{ marginTop: 4 }}>{e.notes}</div> : null}
                    </div>
                    <div style={{ padding: "10px 12px", color: "#64748b", fontSize: 12 }}>
                      {new Date(e.created_at).toLocaleString("en-KE", {
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
  );
}
