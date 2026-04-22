import { useRef, useState, useEffect } from "react";
import { parseMoney, fmtKES } from "../../api/client";

const emojis = {
  Dairy: "🥛",
  Bakery: "🍞",
  Beverages: "🥤",
  Household: "🧴",
  Grocery: "🛒",
};

const getDisplayPrice = (item) => parseMoney(item.selling_price ?? item.price ?? 0);

export default function ProductSearchModal({
  showSearch,
  closeSearch,
  searchQuery,
  setSearchQuery,
  handleSearchKeyDown,
  searchLoading,
  searchResults,
  searchIdx,
  setSearchIdx,
  addProductToCart,
}) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);
  const searchRef = useRef(null);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (!showSearch) return null;

  // Normalize searchResults to always be an array
  const results = Array.isArray(searchResults)
    ? searchResults
    : searchResults?.items || searchResults?.data || searchResults?.products || [];

  const gridLayout = isMobile ? "1fr 80px" : "120px 1fr 120px 100px";

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(3,15,39,.58)", display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: isMobile ? 40 : 70, zIndex: 100, padding: isMobile ? 8 : 0 }}
      onClick={(e) => { if (e.target === e.currentTarget) closeSearch(); }}
    >
      <div className="rms-panel" style={{ width: isMobile ? "100%" : "min(860px, 92vw)", overflow: "hidden" }}>
        <div className="rms-title" style={{ fontSize: isMobile ? 12 : 14 }}>Product Lookup</div>
        <div style={{ padding: isMobile ? 8 : 12 }}>
          <input
            ref={searchRef}
            className="rms-input"
            placeholder={isMobile ? "Search products..." : "Search by name, SKU, description..."}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            style={{ fontSize: isMobile ? 13 : 14, padding: isMobile ? "8px 10px" : "10px 12px" }}
          />
        </div>
        <div style={{ maxHeight: isMobile ? 300 : 420, overflowY: "auto", borderTop: "1px solid #cbd5e1" }}>
          {searchLoading && <div style={{ padding: isMobile ? 16 : 24, textAlign: "center", fontSize: isMobile ? 12 : 14 }}>Searching...</div>}
          {!searchLoading && !results.length && searchQuery && (
            <div style={{ padding: isMobile ? 16 : 24, textAlign: "center", color: "#64748b", fontSize: isMobile ? 12 : 14 }}>No products found.</div>
          )}
          {results.map((p, idx) => (
            <div
              key={p.id}
              onClick={() => { addProductToCart(p); closeSearch(); }}
              onMouseEnter={() => setSearchIdx(idx)}
              style={{
                display: "grid",
                gridTemplateColumns: gridLayout,
                gap: isMobile ? 6 : 8,
                padding: isMobile ? "8px 10px" : "10px 14px",
                borderTop: "1px solid #e2e8f0",
                cursor: "pointer",
                background: searchIdx === idx ? "#dbeafe" : "#fff",
              }}
            >
              {!isMobile && <div style={{ fontSize: isMobile ? 11 : 12 }}>{p.itemcode || p.sku || "—"}</div>}
              <div style={{ fontSize: isMobile ? 11 : 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {!isMobile && `${emojis[p.category?.name] || "🛒"} `}{p.name}
              </div>
              {!isMobile && <div style={{ textAlign: "right", fontSize: 12 }}>{fmtKES(getDisplayPrice(p))}</div>}
              <div style={{ textAlign: "right", color: p.stock_quantity < 10 ? "#b42318" : "#475569", fontSize: isMobile ? 11 : 12 }}>
                {isMobile ? `${p.stock_quantity}` : `Stock ${p.stock_quantity}`}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}