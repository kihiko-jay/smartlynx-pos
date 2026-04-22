import { useState, useEffect } from "react";
import { productsAPI } from "../../../../api/client";
import { shellStyles } from "../../styles";
import { Section, EmptyState, TableShell, Loading } from "../../UIComponents";

export default function CategoriesList({
  onEdit,
  onDelete,
  refreshTrigger,
}) {
  const [categories, setCategories] = useState([]);
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
    loadCategories();
  }, [search, refreshTrigger]);

  useEffect(() => {
    loadCategories();
  }, [skip]);

  const loadCategories = async () => {
    setLoading(true);
    try {
      const params = { skip, limit };
      if (search) params.search = search;

      const result = await productsAPI.categories(params);
      
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
      
      setCategories(items);
      setTotal(total);
    } catch (e) {
      console.error("Failed to load categories:", e);
      setCategories([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const handlePrevPage = () => {
    setSkip(Math.max(0, skip - limit));
  };

  const handleNextPage = () => {
    if (skip + limit < total) {
      setSkip(skip + limit);
    }
  };

  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Search */}
      <Section title="Search">
        <div style={{ padding: isMobile ? "12px 16px" : "16px 20px" }}>
          <input
            type="text"
            placeholder="Search categories..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={shellStyles.searchInput}
          />
        </div>
      </Section>

      {/* Categories Table */}
      <Section title="Categories" right={<span style={{ fontSize: isMobile ? 10 : 12 }}>{total} total</span>}>
        {loading ? (
          <Loading />
        ) : categories.length === 0 ? (
          <EmptyState text="No categories found." />
        ) : (
          <>
            <TableShell headers={["Name", "Parent Category", "Actions"]}>
              {categories.map((cat) => (
                <div
                  key={cat.id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(3, minmax(0,1fr))",
                    borderBottom: "1px solid #cbd5e1",
                    alignItems: "center",
                  }}
                >
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontWeight: 600 }}>
                    {cat.name}
                  </div>
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: 12 }}>
                    {cat.parent_id ? `Category ID: ${cat.parent_id}` : "-"}
                  </div>
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", display: "flex", gap: 6 }}>
                    <button
                      onClick={() => onEdit(cat)}
                      style={shellStyles.smallButton(isMobile)}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Delete category ${cat.name}?`)) {
                          onDelete(cat.id);
                        }
                      }}
                      style={{ ...shellStyles.smallButton(isMobile), background: "#7c2d12" }}
                    >
                      Del
                    </button>
                  </div>
                </div>
              ))}
            </TableShell>

            {/* Pagination */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: isMobile ? "10px 12px" : "12px 16px",
                borderTop: "1px solid #cbd5e1",
                fontSize: isMobile ? 10 : 12,
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <span style={{ color: "#64748b" }}>
                Page {currentPage} of {totalPages}
              </span>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={handlePrevPage}
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
                  onClick={handleNextPage}
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
