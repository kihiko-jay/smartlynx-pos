import { useState, useEffect } from "react";
import { customersAPI, fmtKES } from "../../../../api/client";
import { shellStyles } from "../../styles";
import { Section, EmptyState, TableShell, Loading } from "../../UIComponents";

export default function CustomersList({ onEdit, onView, onDelete, refreshTrigger }) {
  const [customers, setCustomers] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [skip, setSkip] = useState(0);
  const [limit, setLimit] = useState(50);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    setSkip(0);
    loadCustomers();
  }, [search, refreshTrigger]);

  useEffect(() => {
    loadCustomers();
  }, [skip]);

  const loadCustomers = async () => {
    setLoading(true);
    try {
      const params = { skip, limit };
      if (search) params.search = search;
      const result = await customersAPI.list(params);
      
      let items = [];
      let total = 0;
      
      if (Array.isArray(result)) {
        items = result;
        total = result.length;
      } else if (result?.items && Array.isArray(result.items)) {
        items = result.items;
        total = result.total || result.items.length;
      } else if (result?.data && Array.isArray(result.data)) {
        items = result.data;
        total = result.total || result.data.length;
      }
      
      setCustomers(items);
      setTotal(total);
    } catch (e) {
      console.error("Failed to load customers:", e);
      setCustomers([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Section title="Search">
        <div style={{ padding: isMobile ? "12px 16px" : "16px 20px" }}>
          <input
            type="text"
            placeholder="Search customers by name, phone, or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={shellStyles.searchInput}
          />
        </div>
      </Section>

      <Section title="Customers" right={<span style={{ fontSize: isMobile ? 10 : 12 }}>{total} total</span>}>
        {loading ? (
          <Loading />
        ) : customers.length === 0 ? (
          <EmptyState text="No customers found." />
        ) : (
          <>
            <TableShell headers={["Name", "Phone", "Credit Balance", "Loyalty Points", "Actions"]}>
              {customers.map((cust) => (
                <div
                  key={cust.id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(5, minmax(0,1fr))",
                    borderBottom: "1px solid #cbd5e1",
                    alignItems: "center",
                  }}
                >
                  <div style={{ padding: "8px 10px", fontWeight: 600, fontSize: 12 }}>
                    {cust.name}
                  </div>
                  <div style={{ padding: "8px 10px", fontSize: 11 }}>{cust.phone || "-"}</div>
                  <div style={{ padding: "8px 10px", fontSize: 11, fontWeight: 600, color: cust.credit_balance > 0 ? "#dc2626" : "#064e3b" }}>
                    {fmtKES(cust.credit_balance)}
                  </div>
                  <div style={{ padding: "8px 10px", fontSize: 11 }}>{cust.loyalty_points}</div>
                  <div style={{ padding: "8px 10px", display: "flex", gap: 4, fontSize: 10 }}>
                    <button onClick={() => onView(cust)} style={{ ...shellStyles.smallButton(isMobile), background: "#0d58d2", padding: "0 6px" }}>
                      View
                    </button>
                    <button onClick={() => onEdit(cust)} style={{ ...shellStyles.smallButton(isMobile), padding: "0 6px" }}>
                      Edit
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Deactivate customer ${cust.name}?`)) onDelete(cust.id);
                      }}
                      style={{ ...shellStyles.smallButton(isMobile), background: "#7c2d12", padding: "0 6px" }}
                    >
                      Del
                    </button>
                  </div>
                </div>
              ))}
            </TableShell>

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "10px 12px",
                borderTop: "1px solid #cbd5e1",
                fontSize: isMobile ? 10 : 12,
                gap: 8,
              }}
            >
              <span style={{ color: "#64748b" }}>Page {currentPage} of {totalPages}</span>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={() => setSkip(Math.max(0, skip - limit))}
                  disabled={skip === 0}
                  style={{
                    ...shellStyles.smallButton(isMobile),
                    opacity: skip === 0 ? 0.5 : 1,
                    cursor: skip === 0 ? "not-allowed" : "pointer",
                  }}
                >
                  ← Prev
                </button>
                <button
                  onClick={() => setSkip(skip + limit)}
                  disabled={skip + limit >= total}
                  style={{
                    ...shellStyles.smallButton(isMobile),
                    opacity: skip + limit >= total ? 0.5 : 1,
                    cursor: skip + limit >= total ? "not-allowed" : "pointer",
                  }}
                >
                  Next →
                </button>
              </div>
            </div>
          </>
        )}
      </Section>
    </div>
  );
}
