import React from "react";
import { parseMoneyToCents, mulCentsByQty, fmtKESCents } from "../../utils/money";

const emojis = {
  Dairy: "🥛",
  Bakery: "🍞",
  Beverages: "🥤",
  Household: "🧴",
  Grocery: "🛒",
};

const unitCents = (item) => parseMoneyToCents(item.selling_price ?? item.price ?? 0);

// Responsive utilities
const BREAKPOINTS = {
  mobile: 480,
  tablet: 768,
  desktop: 1024,
};

const getGridColumns = (isMobile, isTablet) => {
  if (isMobile) return "40px 1fr 50px 80px 40px"; // #, Item, Qty, Total, Delete
  if (isTablet) return "45px 55px 1fr 55px 100px 120px 45px"; // #, Code, Item, Qty, Price, Total, Delete
  return "50px 60px 1fr 65px 120px 150px 50px"; // Full desktop + Delete
};

export default function CartTable({
  cart,
  selectedCartId,
  setSelectedCartId,
  editingQtyId,
  setEditingQtyId,
  handleQtyChange,
  removeItem,
}) {
  // Detect viewport
  const [isMobile, setIsMobile] = React.useState(typeof window !== "undefined" && window.innerWidth < BREAKPOINTS.tablet);
  const [isTablet, setIsTablet] = React.useState(typeof window !== "undefined" && window.innerWidth < BREAKPOINTS.desktop);

  React.useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < BREAKPOINTS.tablet);
      setIsTablet(window.innerWidth < BREAKPOINTS.desktop);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Handle keyboard shortcuts for cart operations
  React.useEffect(() => {
    const handleKeyDown = (e) => {
      if (selectedCartId && (e.key === "Delete" )) {
        // Only handle Delete/Backspace if not in qty edit mode
        if (editingQtyId === null) {
          e.preventDefault();
          removeItem(selectedCartId);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedCartId, editingQtyId, removeItem]);

  const gridColumns = getGridColumns(isMobile, isTablet);

  // Responsive styles
  const headerStyle = {
    display: "grid",
    gridTemplateColumns: gridColumns,
    background: "#edf4ff",
    borderBottom: "1px solid #cbd5e1",
    fontWeight: 700,
    fontSize: isMobile ? 11 : 12,
    padding: isMobile ? "4px 0" : "6px 0",
  };

  const rowStyle = {
    display: "grid",
    gridTemplateColumns: gridColumns,
    padding: isMobile ? "4px 0" : "6px 0",
    alignItems: "center",
    minHeight: "auto",
  };

  const cellPaddingLeft = isMobile ? 1 : 2;
  const cellPaddingRight = isMobile ? 3 : 6;

  return (
    <div className="rms-panel" style={{ minHeight: 0, display: "flex", flexDirection: "column" }}>
      <div className="rms-title">Current Sale</div>
      <div style={headerStyle}>
        {isMobile ? (
          <><div key="#" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>#</div>
          <div key="Item" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>Item</div>
          <div key="Qty" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>Qty</div>
          <div key="Total" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>Total</div>
          <div key="Delete" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>Del</div></>
        ) : isTablet ? (
          <><div key="#" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>#</div>
          <div key="Code" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>Code</div>
          <div key="Item" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>Item</div>
          <div key="Qty" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>Qty</div>
          <div key="Price" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>Price</div>
          <div key="Total" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>Total</div>
          <div key="Delete" className="rms-cell" style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>Del</div></>
        ) : (
          <>
          {["#", "Code", "Item", "Qty", "Price", "Total", "Delete"].map((h) => (
            <div key={h} className="rms-cell" style={{ paddingTop: 6, paddingBottom: 6, paddingLeft: 6, paddingRight: 6 }}>{h}</div>
          ))}
          </>
        )}
      </div>
      <div style={{ flex: 1, overflowY: "auto", background: "#fff" }}>
        {cart.length === 0 ? (
          <div style={{ padding: isMobile ? 20 : 30, textAlign: "center", color: "#64748b", fontWeight: 700, fontSize: isMobile ? 12 : 14 }}>
            No items in current sale. Scan or type an item code to begin.
          </div>
        ) : (
          cart.map((item, idx) => {
            const uCents = unitCents(item);
            const lineTotalCents = mulCentsByQty(uCents, item.qty);
            const isEditingQty = editingQtyId === item.id;

            return (
              <div
                key={item.id}
                className={`rms-row ${selectedCartId === item.id ? "selected" : ""}`}
                onClick={() => setSelectedCartId(item.id)}
                style={rowStyle}
              >
                <div className="rms-cell" style={{ fontWeight: 700, textAlign: "center", paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight, fontSize: isMobile ? 11 : 12 }}>{idx + 1}</div>
                {!isMobile && <div className="rms-cell" style={{ fontSize: isMobile ? 10 : 11, fontFamily: "monospace", paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>{item.itemcode || item.sku || "—"}</div>}
                <div className="rms-cell" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: isMobile ? 11 : 13, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }} title={item.name}>
                  {!isMobile && `${emojis[item.category?.name] || "🛒"} `}{item.name}
                </div>
                <div className="rms-cell" style={{ textAlign: "center", paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>
                  {isEditingQty ? (
                    <input
                      autoFocus
                      type="number"
                      min="1"
                      value={item.qty}
                      onChange={(e) => handleQtyChange(item.id, e.target.value)}
                      onBlur={() => setEditingQtyId(null)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === "Escape") {
                          setEditingQtyId(null);
                        }
                      }}
                      style={{
                        width: "100%",
                        textAlign: "center",
                        border: "1px solid #92a8c9",
                        borderRadius: 4,
                        padding: isMobile ? "3px 4px" : "4px 6px",
                        fontSize: isMobile ? 11 : 12,
                      }}
                    />
                  ) : (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingQtyId(item.id);
                      }}
                      style={{
                        width: "100%",
                        background: "#eef4ff",
                        border: "1px solid #bfd0ea",
                        borderRadius: 4,
                        padding: isMobile ? "3px 4px" : "4px 6px",
                        cursor: "pointer",
                        fontWeight: 700,
                        fontSize: isMobile ? 11 : 12,
                      }}
                      title="Click to edit quantity"
                    >
                      {item.qty}
                    </button>
                  )}
                </div>
                {!isMobile && <div className="rms-cell" style={{ textAlign: "right", fontSize: isMobile ? 10 : 12, fontWeight: 600, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>{fmtKESCents(uCents)}</div>}
                <div className="rms-cell" style={{ textAlign: "right", fontWeight: 800, color: "#0b5", fontSize: isMobile ? 10 : 12, paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>{fmtKESCents(lineTotalCents)}</div>
                <div className="rms-cell" style={{ textAlign: "center", paddingLeft: cellPaddingLeft, paddingRight: cellPaddingRight }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      removeItem(item.id);
                    }}
                    title="Delete item from cart (or press Delete key)"
                    style={{
                      width: isMobile ? "32px" : "40px",
                      height: isMobile ? "28px" : "32px",
                      background: "#fee2e2",
                      border: "1px solid #fca5a5",
                      borderRadius: 4,
                      cursor: "pointer",
                      fontWeight: 700,
                      fontSize: isMobile ? 14 : 16,
                      color: "#dc2626",
                      padding: 0,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      transition: "all 0.2s",
                    }}
                    onMouseOver={(e) => {
                      e.target.style.background = "#fecaca";
                      e.target.style.borderColor = "#f87171";
                    }}
                    onMouseOut={(e) => {
                      e.target.style.background = "#fee2e2";
                      e.target.style.borderColor = "#fca5a5";
                    }}
                  >
                    ×
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}