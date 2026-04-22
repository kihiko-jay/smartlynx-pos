import { useState, useEffect } from "react";
import { productsAPI, fmtKES } from "../../../../api/client";
import { shellStyles } from "../../styles";
import { Section, EmptyState, Loading } from "../../UIComponents";

export default function ProductDetailDrawer({
  product,
  onEdit,
  onClose,
}) {
  const [stockHistory, setStockHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (product?.id) {
      loadStockHistory();
    }
  }, [product?.id]);

  const loadStockHistory = async () => {
    setLoadingHistory(true);
    try {
      const history = await productsAPI.stockHistory(product.id);
      setStockHistory(Array.isArray(history) ? history.slice(0, 10) : []);
    } catch (e) {
      console.warn("Failed to load stock history:", e);
      setStockHistory([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  if (!product) {
    return null;
  }

  const markup = product.selling_price - (product.cost_price || 0);
  const marginPercent = product.cost_price 
    ? ((markup / product.cost_price) * 100).toFixed(1)
    : 0;

  return (
    <div
      style={{
        position: "fixed",
        right: 0,
        top: 0,
        width: isMobile ? "100%" : "400px",
        height: "100vh",
        background: "#fff",
        boxShadow: "-2px 0 8px rgba(0,0,0,0.15)",
        zIndex: 1000,
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <div
        style={{
          ...shellStyles.panelTitle(isMobile),
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: isMobile ? "10px 12px" : "12px 16px",
        }}
      >
        <span>{product.sku}</span>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "#fff",
            fontSize: 20,
            cursor: "pointer",
            padding: "4px 8px",
          }}
        >
          ✕
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: isMobile ? "12px 12px" : "16px 16px" }}>
        {/* Basic Info */}
        <Section title="Product Info">
          <div style={{ display: "grid", gap: 12 }}>
            <div>
              <div
                style={{
                  fontSize: 10,
                  color: "#64748b",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  marginBottom: 4,
                }}
              >
                Name
              </div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{product.name}</div>
            </div>

            {product.description && (
              <div>
                <div
                  style={{
                    fontSize: 10,
                    color: "#64748b",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    marginBottom: 4,
                  }}
                >
                  Description
                </div>
                <div style={{ fontSize: 12 }}>{product.description}</div>
              </div>
            )}

            <div>
              <div
                style={{
                  fontSize: 10,
                  color: "#64748b",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  marginBottom: 4,
                }}
              >
                Category
              </div>
              <div style={{ fontSize: 12 }}>{product.category?.name || "-"}</div>
            </div>

            <div>
              <div
                style={{
                  fontSize: 10,
                  color: "#64748b",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  marginBottom: 4,
                }}
              >
                Supplier
              </div>
              <div style={{ fontSize: 12 }}>{product.supplier?.name || "-"}</div>
            </div>
          </div>
        </Section>

        {/* Pricing */}
        <Section title="Pricing & Margin" style={{ marginTop: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <div
                style={{
                  fontSize: 10,
                  color: "#64748b",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  marginBottom: 4,
                }}
              >
                Cost Price
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "#666" }}>
                {product.cost_price ? fmtKES(product.cost_price) : "-"}
              </div>
            </div>

            <div>
              <div
                style={{
                  fontSize: 10,
                  color: "#64748b",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  marginBottom: 4,
                }}
              >
                Selling Price
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "#047857" }}>
                {fmtKES(product.selling_price)}
              </div>
            </div>

            {product.cost_price > 0 && (
              <>
                <div>
                  <div
                    style={{
                      fontSize: 10,
                      color: "#64748b",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      marginBottom: 4,
                    }}
                  >
                    Markup
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#0d58d2" }}>
                    {fmtKES(markup)}
                  </div>
                </div>

                <div>
                  <div
                    style={{
                      fontSize: 10,
                      color: "#64748b",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      marginBottom: 4,
                    }}
                  >
                    Margin %
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#0d58d2" }}>
                    {marginPercent}%
                  </div>
                </div>
              </>
            )}
          </div>
        </Section>

        {/* Stock Info */}
        <Section title="Stock Info" style={{ marginTop: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <div
                style={{
                  fontSize: 10,
                  color: "#64748b",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  marginBottom: 4,
                }}
              >
                Current Stock
              </div>
              <div
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  color: product.is_low_stock ? "#dc2626" : "#111827",
                }}
              >
                {product.stock_quantity} {product.unit}
              </div>
            </div>

            <div>
              <div
                style={{
                  fontSize: 10,
                  color: "#64748b",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  marginBottom: 4,
                }}
              >
                Reorder Level
              </div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{product.reorder_level}</div>
            </div>

            {product.stock_value !== undefined && (
              <div style={{ gridColumn: "1 / -1" }}>
                <div
                  style={{
                    fontSize: 10,
                    color: "#64748b",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    marginBottom: 4,
                  }}
                >
                  Total Stock Value
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, color: "#047857" }}>
                  {fmtKES(product.stock_value)}
                </div>
              </div>
            )}
          </div>
        </Section>

        {/* Tax Info */}
        <Section title="Tax & Unit" style={{ marginTop: 12 }}>
          <div style={{ display: "grid", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <div style={{ fontSize: 12, color: "#64748b" }}>Tax Code:</div>
              <div style={{ fontSize: 12, fontWeight: 600 }}>{product.tax_code}</div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <div style={{ fontSize: 12, color: "#64748b" }}>VAT Exempt:</div>
              <div style={{ fontSize: 12, fontWeight: 600 }}>
                {product.vat_exempt ? "Yes" : "No"}
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <div style={{ fontSize: 12, color: "#64748b" }}>Unit:</div>
              <div style={{ fontSize: 12, fontWeight: 600 }}>{product.unit}</div>
            </div>
          </div>
        </Section>

        {/* Stock History */}
        <Section title="Recent Stock Movements" style={{ marginTop: 12 }}>
          {loadingHistory ? (
            <EmptyState text="Loading..." />
          ) : stockHistory.length === 0 ? (
            <EmptyState text="No stock movements yet." />
          ) : (
            <div style={{ display: "grid", gap: 8, fontSize: 11 }}>
              {stockHistory.map((movement, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: "8px 10px",
                    background: "#f9fafb",
                    borderRadius: 4,
                    borderLeft: `3px solid ${
                      movement.qty_delta > 0 ? "#047857" : "#dc2626"
                    }`,
                  }}
                >
                  <div style={{ fontWeight: 600, marginBottom: 2 }}>
                    {movement.movement_type}
                  </div>
                  <div style={{ color: "#64748b" }}>
                    {movement.qty_delta > 0 ? "+" : "-"}{Math.abs(movement.qty_delta)} → {movement.qty_after}
                  </div>
                  {movement.notes && (
                    <div style={{ color: "#94a3b8", marginTop: 2 }}>
                      {movement.notes}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>

      {/* Footer Actions */}
      <div
        style={{
          display: "flex",
          gap: 8,
          padding: isMobile ? "10px 12px" : "12px 16px",
          borderTop: "1px solid #cbd5e1",
          background: "#f9fafb",
        }}
      >
        <button
          onClick={() => {
            onEdit(product);
            onClose();
          }}
          style={shellStyles.primaryButton(isMobile)}
        >
          Edit
        </button>
        <button
          onClick={onClose}
          style={{
            ...shellStyles.smallButton(isMobile),
            background: "#6b7280",
            flex: 1,
          }}
        >
          Close
        </button>
      </div>
    </div>
  );
}
