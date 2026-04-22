import { useState, useEffect } from "react";
import { productsAPI, fmtKES } from "../../../../api/client";
import { shellStyles } from "../../styles";
import { Section, EmptyState, TableShell, Loading } from "../../UIComponents";

export default function ProductsList({
  onEdit,
  onView,
  onDelete,
  onRefresh,
  refreshTrigger,
}) {
  const [products, setProducts] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState(null);
  const [supplierId, setSupplierId] = useState(null);
  const [lowStock, setLowStock] = useState(false);
  const [skip, setSkip] = useState(0);
  const [limit, setLimit] = useState(50);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);
  const [categories, setCategories] = useState([]);
  const [suppliers, setSuppliers] = useState([]);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    loadCategories();
    loadSuppliers();
  }, []);

  useEffect(() => {
    setSkip(0); // Reset pagination when filters change
    loadProducts();
  }, [search, categoryId, supplierId, lowStock, refreshTrigger]);

  useEffect(() => {
    loadProducts();
  }, [skip]);

  const loadCategories = async () => {
    try {
      const result = await productsAPI.categories();
      const list = Array.isArray(result) ? result : (result?.items || result?.data || []);
      setCategories(Array.isArray(list) ? list : []);
    } catch (e) {
      console.error("Failed to load categories:", e.message);
      setCategories([]);
    }
  };

  const loadSuppliers = async () => {
    try {
      const result = await productsAPI.suppliers();
      const list = Array.isArray(result) ? result : (result?.items || result?.data || []);
      setSuppliers(Array.isArray(list) ? list : []);
    } catch (e) {
      console.error("Failed to load suppliers:", e.message);
      setSuppliers([]);
    }
  };

  const loadProducts = async () => {
    setLoading(true);
    try {
      const params = {
        skip,
        limit,
      };
      if (search) params.search = search;
      if (categoryId) params.category_id = categoryId;
      if (supplierId) params.supplier_id = supplierId;
      if (lowStock) params.low_stock = true;

      const result = await productsAPI.list(params);
      
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
      } else if (result?.products && Array.isArray(result.products)) {
        items = result.products;
        total = result.total || result.products.length;
      }
      
      setProducts(items);
      setTotal(total);
    } catch (e) {
      console.error("Failed to load products:", e);
      setProducts([]);
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
  const startIndex = skip + 1;
  const endIndex = Math.min(skip + limit, total);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Filters */}
      <Section title="Filters" style={{ ...shellStyles.panel }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr" : "repeat(auto-fit, minmax(200px, 1fr))",
            gap: 12,
            padding: isMobile ? "12px 16px" : "16px 20px",
          }}
        >
          <input
            type="text"
            placeholder="Search products..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={shellStyles.searchInput}
          />
          <select
            value={categoryId || ""}
            onChange={(e) => setCategoryId(e.target.value ? parseInt(e.target.value) : null)}
            style={shellStyles.searchInput}
          >
            <option value="">All Categories</option>
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.name}
              </option>
            ))}
          </select>
          <select
            value={supplierId || ""}
            onChange={(e) => setSupplierId(e.target.value ? parseInt(e.target.value) : null)}
            style={shellStyles.searchInput}
          >
            <option value="">All Suppliers</option>
            {suppliers.map((sup) => (
              <option key={sup.id} value={sup.id}>
                {sup.name}
              </option>
            ))}
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="checkbox"
              checked={lowStock}
              onChange={(e) => setLowStock(e.target.checked)}
            />
            <span
              style={{ fontSize: isMobile ? 11 : 13, cursor: "pointer", userSelect: "none" }}
            >
              Low Stock Only
            </span>
          </label>
        </div>
      </Section>

      {/* Products Table */}
      <Section
        title="Products"
        right={
          <span style={{ fontSize: isMobile ? 10 : 12, color: "#64748b" }}>
            {total} total
          </span>
        }
      >
        {loading ? (
          <Loading />
        ) : products.length === 0 ? (
          <EmptyState text="No products found." />
        ) : (
          <>
            <TableShell
              headers={[
                "SKU",
                "Name",
                "Category",
                "Price",
                "Stock",
                "Actions",
              ]}
              hideColumns={isMobile ? [2, 3, 4] : []}
            >
              {products.map((product) => (
                <div
                  key={product.id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${
                      isMobile ? 3 : 6
                    }, minmax(0,1fr))`,
                    borderBottom: "1px solid #cbd5e1",
                    alignItems: "center",
                  }}
                >
                  <div
                    style={{
                      padding: isMobile ? "8px 10px" : "10px 12px",
                      fontSize: isMobile ? 10 : 12,
                      fontWeight: 600,
                    }}
                  >
                    {product.sku}
                  </div>
                  {!isMobile && (
                    <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: 12 }}>
                      {product.name}
                    </div>
                  )}
                  {!isMobile && (
                    <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: 12 }}>
                      {product.category?.name || "-"}
                    </div>
                  )}
                  {!isMobile && (
                    <div
                      style={{
                        padding: isMobile ? "8px 10px" : "10px 12px",
                        fontSize: 12,
                        fontWeight: 600,
                        color: "#047857",
                      }}
                    >
                      {fmtKES(product.selling_price)}
                    </div>
                  )}
                  {!isMobile && (
                    <div
                      style={{
                        padding: isMobile ? "8px 10px" : "10px 12px",
                        fontSize: 12,
                        fontWeight: 600,
                        color: product.is_low_stock ? "#dc2626" : "#111827",
                      }}
                    >
                      {product.stock_quantity}
                      {product.is_low_stock && (
                        <span style={{ fontSize: 10, marginLeft: 4 }}>⚠️</span>
                      )}
                    </div>
                  )}
                  {isMobile && (
                    <div style={{ padding: "8px 10px", fontSize: 10 }}>
                      <div style={{ fontWeight: 600 }}>{product.name}</div>
                      <div style={{ color: "#64748b" }}>
                        {fmtKES(product.selling_price)} · Stock: {product.stock_quantity}
                      </div>
                    </div>
                  )}
                  <div
                    style={{
                      padding: isMobile ? "8px 10px" : "10px 12px",
                      display: "flex",
                      gap: 6,
                      justifyContent: isMobile ? "flex-end" : "center",
                    }}
                  >
                    <button
                      onClick={() => onView(product)}
                      style={{
                        ...shellStyles.smallButton(isMobile),
                        background: "#0d58d2",
                      }}
                    >
                      View
                    </button>
                    <button
                      onClick={() => onEdit(product)}
                      style={shellStyles.smallButton(isMobile)}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Delete product ${product.sku}?`)) {
                          onDelete(product.id);
                        }
                      }}
                      style={{
                        ...shellStyles.smallButton(isMobile),
                        background: "#7c2d12",
                      }}
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
                Showing {startIndex}-{endIndex} of {total}
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
                <span style={{ padding: "6px 8px", fontSize: 11 }}>
                  Page {currentPage} of {totalPages}
                </span>
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
