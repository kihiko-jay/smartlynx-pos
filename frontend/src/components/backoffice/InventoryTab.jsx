import { useState, useEffect } from "react";
import { productsAPI, fmtKES, parseMoney } from "../../api/client";
import { shellStyles } from "./styles";
import { Section, EmptyState, TableShell } from "./UIComponents";

export default function InventoryTab() {
  const [products, setProducts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [categories, setCategories] = useState([]);
  const [search, setSearch] = useState("");
  const [lowStock, setLowStock] = useState(false);
  const [loading, setLoading] = useState(false);
  const [editId, setEditId] = useState(null);
  const [editPrice, setEditPrice] = useState("");
  const [saving, setSaving] = useState(false);
  const [histProduct, setHistProduct] = useState(null);
  const [history, setHistory] = useState([]);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);
  
  // Product add modal state
  const [showAddProduct, setShowAddProduct] = useState(false);
  const [newProduct, setNewProduct] = useState({
    sku: "",
    name: "",
    selling_price: "",
    cost_price: "",
    barcode: "",
    itemcode: "",
    category_id: null,
    supplier_id: null,
    stock_quantity: "0",
    reorder_level: "10",
    description: "",
  });
  const [addProductError, setAddProductError] = useState("");
  const [addProductLoading, setAddProductLoading] = useState(false);

  // Supplier add modal state
  const [showAddSupplier, setShowAddSupplier] = useState(false);
  const [newSupplier, setNewSupplier] = useState({
    name: "",
    contact_name: "",
    phone: "",
    email: "",
    address: "",
    kra_pin: "",
  });
  const [addSupplierError, setAddSupplierError] = useState("");
  const [addSupplierLoading, setAddSupplierLoading] = useState(false);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    loadProducts();
  }, [search, lowStock]);

  const loadInitialData = async () => {
    try {
      const [supp, cats] = await Promise.all([
        productsAPI.suppliers(),
        productsAPI.categories(),
      ]);
      
      // Handle different API response formats
      const suppliersList = Array.isArray(supp) ? supp : (supp?.items || supp?.data ? supp?.items || supp?.data : []);
      const categoriesList = Array.isArray(cats) ? cats : (cats?.items || cats?.data ? cats?.items || cats?.data : []);
      
      setSuppliers(suppliersList);
      setCategories(categoriesList);
    } catch (e) {
      console.warn("Failed to load suppliers/categories:", e.message);
      setSuppliers([]);
      setCategories([]);
    }
    loadProducts();
  };

  const loadProducts = async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (search) params.search = search;
      if (lowStock) params.low_stock = true;
      const result = await productsAPI.list(params);
      // Handle different API response formats
      if (Array.isArray(result)) {
        setProducts(result);
      } else if (result?.data && Array.isArray(result.data)) {
        setProducts(result.data);
      } else if (result?.products && Array.isArray(result.products)) {
        setProducts(result.products);
      } else if (result?.items && Array.isArray(result.items)) {
        setProducts(result.items);
      } else {
        console.warn("Unexpected API response format for products:", result);
        setProducts(Array.isArray(result) ? result : []);
      }
    } catch (e) {
      console.error("Failed to load products:", e.message);
      setProducts([]);
    } finally {
      setLoading(false);
    }
  };

  const savePrice = async (id) => {
    setSaving(true);
    try {
      await productsAPI.update(id, { selling_price: editPrice });
      setEditId(null);
      loadProducts();
    } catch (e) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  };

  const loadHistory = async (p) => {
    setHistProduct(p);
    try {
      setHistory(await productsAPI.stockHistory(p.id));
    } catch {
      setHistory([]);
    }
  };

  const handleAddProduct = async () => {
    setAddProductError("");
    if (!newProduct.sku.trim()) {
      setAddProductError("SKU is required");
      return;
    }
    if (!newProduct.name.trim()) {
      setAddProductError("Product name is required");
      return;
    }
    if (!newProduct.selling_price || parseFloat(newProduct.selling_price) <= 0) {
      setAddProductError("Selling price must be greater than 0");
      return;
    }

    setAddProductLoading(true);
    try {
      const payload = {
        ...newProduct,
        selling_price: parseFloat(newProduct.selling_price),
        cost_price: newProduct.cost_price ? parseFloat(newProduct.cost_price) : null,
        stock_quantity: parseInt(newProduct.stock_quantity) || 0,
        reorder_level: parseInt(newProduct.reorder_level) || 10,
        category_id: newProduct.category_id ? parseInt(newProduct.category_id) : null,
        supplier_id: newProduct.supplier_id ? parseInt(newProduct.supplier_id) : null,
        itemcode: newProduct.itemcode ? parseInt(newProduct.itemcode) : null,
      };
      await productsAPI.create(payload);
      setShowAddProduct(false);
      setNewProduct({
        sku: "",
        name: "",
        selling_price: "",
        cost_price: "",
        barcode: "",
        itemcode: "",
        category_id: null,
        supplier_id: null,
        stock_quantity: "0",
        reorder_level: "10",
        description: "",
      });
      loadProducts();
    } catch (e) {
      setAddProductError(e.message);
    } finally {
      setAddProductLoading(false);
    }
  };

  const handleAddSupplier = async () => {
    setAddSupplierError("");
    if (!newSupplier.name.trim()) {
      setAddSupplierError("Supplier name is required");
      return;
    }

    setAddSupplierLoading(true);
    try {
      const supplier = await productsAPI.createSupplier(newSupplier);
      setSuppliers([...suppliers, supplier]);
      setShowAddSupplier(false);
      setNewSupplier({
        name: "",
        contact_name: "",
        phone: "",
        email: "",
        address: "",
        kra_pin: "",
      });
    } catch (e) {
      setAddSupplierError(e.message);
    } finally {
      setAddSupplierLoading(false);
    }
  };

  return (
    <div style={{ display: "grid", gap: isMobile ? 12 : 16 }}>
      <Section
        title="Inventory Controls"
        right={
          <span style={{ fontSize: isMobile ? 9 : 11, color: "#dbeafe" }}>
            {products.length} products
          </span>
        }
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr" : "1fr auto auto auto auto",
            gap: isMobile ? 8 : 10,
            alignItems: "center",
          }}
        >
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search products..."
            style={shellStyles.searchInput}
          />
          {!isMobile && (
            <>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                <input
                  type="checkbox"
                  checked={lowStock}
                  onChange={(e) => setLowStock(e.target.checked)}
                />{" "}
                Low stock only
              </label>
              <button style={shellStyles.smallButton(isMobile)} onClick={loadProducts}>
                Refresh
              </button>
              <button
                style={{
                  ...shellStyles.smallButton(isMobile),
                  background: "#15803d",
                  borderColor: "#15803d",
                }}
                onClick={() => setShowAddProduct(true)}
              >
                + Add Product
              </button>
              <button
                style={{
                  ...shellStyles.smallButton(isMobile),
                  background: "#7c3aed",
                  borderColor: "#7c3aed",
                }}
                onClick={() => setShowAddSupplier(true)}
              >
                Suppliers
              </button>
            </>
          )}
          {isMobile && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8 }}>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 11,
                  fontWeight: 700,
                }}
              >
                <input
                  type="checkbox"
                  checked={lowStock}
                  onChange={(e) => setLowStock(e.target.checked)}
                />{" "}
                Low stock
              </label>
              <button style={shellStyles.smallButton(isMobile)} onClick={loadProducts}>
                Refresh
              </button>
            </div>
          )}
          {isMobile && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <button
                style={{
                  ...shellStyles.smallButton(isMobile),
                  background: "#15803d",
                  borderColor: "#15803d",
                }}
                onClick={() => setShowAddProduct(true)}
              >
                + Add
              </button>
              <button
                style={{
                  ...shellStyles.smallButton(isMobile),
                  background: "#7c3aed",
                  borderColor: "#7c3aed",
                }}
                onClick={() => setShowAddSupplier(true)}
              >
                Suppliers
              </button>
            </div>
          )}
        </div>
      </Section>

      {histProduct ? (
        <Section
          title={`Stock History · ${histProduct.name}`}
          right={
            <button
              style={shellStyles.smallButton(isMobile)}
              onClick={() => setHistProduct(null)}
            >
              Close
            </button>
          }
        >
          <TableShell headers={["Date", "Type", "Delta", "Before", "After", "Ref"]} hideColumns={isMobile ? [4, 5] : []}>
            {(history || []).map((m, idx) => {
              const displayCols = isMobile ? ["Date", "Type", "Delta", "Before"] : ["Date", "Type", "Delta", "Before", "After", "Ref"];
              return (
                <div
                  key={m.id || idx}
                  style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${displayCols.length}, minmax(0,1fr))`,
                    borderTop: idx ? "1px solid #e2e8f0" : "none",
                    background: idx % 2 ? "#f8fbff" : "#fff",
                  }}
                >
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", color: "#64748b", fontSize: isMobile ? 10 : 12 }}>
                    {new Date(m.created_at).toLocaleString("en-KE", {
                      dateStyle: "short",
                      timeStyle: "short",
                    })}
                  </div>
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", textTransform: "uppercase", fontWeight: 700, fontSize: isMobile ? 10 : 12 }}>
                    {m.movement_type}
                  </div>
                  <div
                    style={{
                      padding: isMobile ? "8px 10px" : "10px 12px",
                      color: m.qty_delta > 0 ? "#15803d" : "#b42318",
                      fontWeight: 700,
                      fontSize: isMobile ? 10 : 12,
                    }}
                  >
                    {m.qty_delta > 0 ? "+" : ""}
                    {m.qty_delta}
                  </div>
                  <div style={{ padding: isMobile ? "8px 10px" : "10px 12px", fontSize: isMobile ? 10 : 12 }}>{m.qty_before}</div>
                  {!isMobile && (
                    <>
                      <div style={{ padding: "10px 12px", fontWeight: 700, fontSize: 12 }}>
                        {m.qty_after}
                      </div>
                      <div style={{ padding: "10px 12px", color: "#64748b", fontSize: 12 }}>
                        {m.ref_id || "—"}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </TableShell>
        </Section>
      ) : null}

      <Section title="Products Grid">
        {loading ? (
          <EmptyState text="Loading inventory..." />
        ) : isMobile ? (
          <>
            {products.map((p, idx) => (
              <div
                key={p.id}
                style={{
                  border: "1px solid #cbd5e1",
                  borderRadius: 8,
                  padding: 12,
                  marginBottom: idx < products.length - 1 ? 10 : 0,
                  background: "#fff",
                }}
              >
                <div style={{ fontWeight: 700, fontSize: 12 }}>
                  {p.name}
                </div>
                <div style={{ fontSize: 10, color: "#64748b", marginTop: 4 }}>
                  SKU: {p.sku}
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 8,
                    marginTop: 8,
                  }}
                >
                  <div>
                    <div style={{ fontSize: 9, color: "#64748b", textTransform: "uppercase" }}>Price</div>
                    {editId === p.id ? (
                      <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                        <input
                          value={editPrice}
                          onChange={(e) => setEditPrice(e.target.value)}
                          style={{
                            ...shellStyles.searchInput,
                            padding: "4px 6px",
                            fontSize: 11,
                          }}
                        />
                        <button
                          style={{ ...shellStyles.primaryButton(isMobile), flex: 1 }}
                          disabled={saving}
                          onClick={() => savePrice(p.id)}
                        >
                          Save
                        </button>
                      </div>
                    ) : (
                      <button
                        style={{
                          background: "none",
                          border: "none",
                          padding: 0,
                          cursor: "pointer",
                          color: "#155eef",
                          fontWeight: 700,
                          fontSize: 12,
                        }}
                        onClick={() => {
                          setEditId(p.id);
                          setEditPrice(parseMoney(p.selling_price).toFixed(2));
                        }}
                      >
                        {fmtKES(p.selling_price)}
                      </button>
                    )}
                  </div>
                  <div>
                    <div style={{ fontSize: 9, color: "#64748b", textTransform: "uppercase" }}>Stock</div>
                    <div
                      style={{
                        fontSize: 12,
                        fontWeight: 700,
                        marginTop: 4,
                        color: p.is_low_stock ? "#b42318" : "#111827",
                      }}
                    >
                      {p.stock_quantity}{" "}
                      <span
                        style={{
                          fontSize: 9,
                          fontWeight: 700,
                          color:
                            p.stock_quantity === 0
                              ? "#b42318"
                              : p.is_low_stock
                              ? "#c2410c"
                              : "#15803d",
                        }}
                      >
                        {p.stock_quantity === 0 ? "OUT" : p.is_low_stock ? "LOW" : "OK"}
                      </span>
                    </div>
                  </div>
                </div>
                <button
                  style={{
                    ...shellStyles.smallButton(isMobile),
                    width: "100%",
                    marginTop: 8,
                  }}
                  onClick={() => loadHistory(p)}
                >
                  History
                </button>
              </div>
            ))}
          </>
        ) : (
          <div
            style={{
              border: "1px solid #cbd5e1",
              borderRadius: 8,
              overflow: "hidden",
              background: "#fff",
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "110px 1.5fr 1fr 1fr 1fr 100px 120px 100px",
                background: "#edf4ff",
                borderBottom: "1px solid #cbd5e1",
                fontWeight: 700,
                fontSize: 11,
                textTransform: "uppercase",
                color: "#334155",
              }}
            >
              {["SKU", "Product", "Category", "Price", "Cost", "Stock", "Status", "Actions"].map(
                (h) => (
                  <div key={h} style={{ padding: "10px 12px" }}>
                    {h}
                  </div>
                )
              )}
            </div>
            {products.map((p, idx) => (
              <div
                key={p.id}
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "110px 1.5fr 1fr 1fr 1fr 100px 120px 100px",
                  borderTop: idx ? "1px solid #e2e8f0" : "none",
                  background: idx % 2 ? "#f8fbff" : "#fff",
                  alignItems: "center",
                }}
              >
                <div style={{ padding: "10px 12px", color: "#64748b" }}>
                  {p.sku}
                </div>
                <div style={{ padding: "10px 12px", fontWeight: 700 }}>
                  {p.name}
                </div>
                <div style={{ padding: "10px 12px", color: "#64748b" }}>
                  {p.category?.name || "—"}
                </div>
                <div style={{ padding: "10px 12px" }}>
                  {editId === p.id ? (
                    <div style={{ display: "flex", gap: 6 }}>
                      <input
                        value={editPrice}
                        onChange={(e) => setEditPrice(e.target.value)}
                        style={{
                          ...shellStyles.searchInput,
                          padding: "6px 8px",
                          fontSize: 12,
                        }}
                      />
                      <button
                        style={shellStyles.primaryButton(false)}
                        disabled={saving}
                        onClick={() => savePrice(p.id)}
                      >
                        Save
                      </button>
                    </div>
                  ) : (
                    <button
                      style={{
                        background: "none",
                        border: "none",
                        padding: 0,
                        cursor: "pointer",
                        color: "#155eef",
                        fontWeight: 700,
                      }}
                      onClick={() => {
                        setEditId(p.id);
                        setEditPrice(parseMoney(p.selling_price).toFixed(2));
                      }}
                    >
                      {fmtKES(p.selling_price)}
                    </button>
                  )}
                </div>
                <div style={{ padding: "10px 12px", color: "#64748b" }}>
                  {p.cost_price ? fmtKES(p.cost_price) : "—"}
                </div>
                <div
                  style={{
                    padding: "10px 12px",
                    color: p.is_low_stock ? "#b42318" : "#111827",
                    fontWeight: 700,
                  }}
                >
                  {p.stock_quantity}
                </div>
                <div style={{ padding: "10px 12px" }}>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      color:
                        p.stock_quantity === 0
                          ? "#b42318"
                          : p.is_low_stock
                          ? "#c2410c"
                          : "#15803d",
                    }}
                  >
                    {p.stock_quantity === 0 ? "OUT" : p.is_low_stock ? "LOW" : "OK"}
                  </span>
                </div>
                <div style={{ padding: "10px 12px" }}>
                  <button
                    style={shellStyles.smallButton(false)}
                    onClick={() => loadHistory(p)}
                  >
                    History
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Suppliers Management Section */}
      <Section title="Suppliers">
        {suppliers.length === 0 ? (
          <EmptyState text="No suppliers yet. Add one to get started." />
        ) : (
          <div
            style={{
              border: "1px solid #cbd5e1",
              borderRadius: 8,
              overflow: "hidden",
              background: "#fff",
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr 1fr 1fr 1fr",
                background: "#edf4ff",
                borderBottom: "1px solid #cbd5e1",
                fontWeight: 700,
                fontSize: 11,
                textTransform: "uppercase",
                color: "#334155",
              }}
            >
              {(isMobile ? ["Name", "Contact"] : ["Name", "Contact", "Phone", "Email"]).map((h) => (
                <div key={h} style={{ padding: "10px 12px" }}>
                  {h}
                </div>
              ))}
            </div>
            {suppliers.map((s, idx) => (
              <div
                key={s.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr 1fr 1fr 1fr",
                  borderTop: idx ? "1px solid #e2e8f0" : "none",
                  background: idx % 2 ? "#f8fbff" : "#fff",
                  alignItems: "center",
                }}
              >
                <div style={{ padding: "10px 12px", fontWeight: 700 }}>
                  {s.name}
                </div>
                <div style={{ padding: "10px 12px", color: "#64748b", fontSize: 12 }}>
                  {s.contact_name || "—"}
                </div>
                {!isMobile && (
                  <>
                    <div style={{ padding: "10px 12px", color: "#64748b", fontSize: 12 }}>
                      {s.phone || "—"}
                    </div>
                    <div style={{ padding: "10px 12px", color: "#64748b", fontSize: 12 }}>
                      {s.email || "—"}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Add Product Modal */}
      {showAddProduct && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: isMobile ? 16 : 0,
          }}
          onClick={() => setShowAddProduct(false)}
        >
          <div
            style={{
              background: "#fff",
              borderRadius: 12,
              padding: isMobile ? 16 : 24,
              maxWidth: isMobile ? "100%" : 500,
              maxHeight: "90vh",
              overflowY: "auto",
              boxShadow: "0 20px 25px rgba(0,0,0,0.15)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ fontWeight: 800, fontSize: isMobile ? 16 : 18, marginBottom: 16 }}>
              Add New Product
            </div>

            {addProductError && (
              <div
                style={{
                  background: "#fee2e2",
                  border: "1px solid #fecaca",
                  color: "#dc2626",
                  padding: 12,
                  borderRadius: 6,
                  marginBottom: 16,
                  fontSize: 12,
                }}
              >
                {addProductError}
              </div>
            )}

            <div style={{ display: "grid", gap: 12 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>SKU *</label>
                <input
                  type="text"
                  value={newProduct.sku}
                  onChange={(e) => setNewProduct({ ...newProduct, sku: e.target.value })}
                  placeholder="e.g. PROD001"
                  style={{
                    ...shellStyles.searchInput,
                    marginTop: 6,
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Product Name *</label>
                <input
                  type="text"
                  value={newProduct.name}
                  onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })}
                  placeholder="Product name"
                  style={{
                    ...shellStyles.searchInput,
                    marginTop: 6,
                  }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Selling Price *</label>
                  <input
                    type="number"
                    step="0.01"
                    value={newProduct.selling_price}
                    onChange={(e) => setNewProduct({ ...newProduct, selling_price: e.target.value })}
                    placeholder="0.00"
                    style={{
                      ...shellStyles.searchInput,
                      marginTop: 6,
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Cost Price</label>
                  <input
                    type="number"
                    step="0.01"
                    value={newProduct.cost_price}
                    onChange={(e) => setNewProduct({ ...newProduct, cost_price: e.target.value })}
                    placeholder="0.00"
                    style={{
                      ...shellStyles.searchInput,
                      marginTop: 6,
                    }}
                  />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Stock Qty</label>
                  <input
                    type="number"
                    value={newProduct.stock_quantity}
                    onChange={(e) => setNewProduct({ ...newProduct, stock_quantity: e.target.value })}
                    placeholder="0"
                    style={{
                      ...shellStyles.searchInput,
                      marginTop: 6,
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Reorder Level</label>
                  <input
                    type="number"
                    value={newProduct.reorder_level}
                    onChange={(e) => setNewProduct({ ...newProduct, reorder_level: e.target.value })}
                    placeholder="10"
                    style={{
                      ...shellStyles.searchInput,
                      marginTop: 6,
                    }}
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Barcode</label>
                <input
                  type="text"
                  value={newProduct.barcode}
                  onChange={(e) => setNewProduct({ ...newProduct, barcode: e.target.value })}
                  placeholder="Optional"
                  style={{
                    ...shellStyles.searchInput,
                    marginTop: 6,
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Item Code</label>
                <input
                  type="number"
                  value={newProduct.itemcode}
                  onChange={(e) => setNewProduct({ ...newProduct, itemcode: e.target.value })}
                  placeholder="Optional numeric code"
                  style={{
                    ...shellStyles.searchInput,
                    marginTop: 6,
                  }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Category</label>
                  <select
                    value={newProduct.category_id || ""}
                    onChange={(e) => setNewProduct({ ...newProduct, category_id: e.target.value })}
                    style={{
                      ...shellStyles.searchInput,
                      marginTop: 6,
                    }}
                  >
                    <option value="">— None —</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Supplier</label>
                  <select
                    value={newProduct.supplier_id || ""}
                    onChange={(e) => setNewProduct({ ...newProduct, supplier_id: e.target.value })}
                    style={{
                      ...shellStyles.searchInput,
                      marginTop: 6,
                    }}
                  >
                    <option value="">— None —</option>
                    {suppliers.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Description</label>
                <textarea
                  value={newProduct.description}
                  onChange={(e) => setNewProduct({ ...newProduct, description: e.target.value })}
                  placeholder="Product description"
                  style={{
                    ...shellStyles.searchInput,
                    marginTop: 6,
                    minHeight: 80,
                    fontFamily: "inherit",
                  }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 16 }}>
                <button
                  style={{
                    ...shellStyles.smallButton(false),
                    borderColor: "#cbd5e1",
                    color: "#334155",
                  }}
                  onClick={() => setShowAddProduct(false)}
                  disabled={addProductLoading}
                >
                  Cancel
                </button>
                <button
                  style={{
                    ...shellStyles.smallButton(false),
                    background: "#15803d",
                    borderColor: "#15803d",
                  }}
                  onClick={handleAddProduct}
                  disabled={addProductLoading}
                >
                  {addProductLoading ? "Creating..." : "Create Product"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Supplier Modal */}
      {showAddSupplier && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: isMobile ? 16 : 0,
          }}
          onClick={() => setShowAddSupplier(false)}
        >
          <div
            style={{
              background: "#fff",
              borderRadius: 12,
              padding: isMobile ? 16 : 24,
              maxWidth: isMobile ? "100%" : 500,
              boxShadow: "0 20px 25px rgba(0,0,0,0.15)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ fontWeight: 800, fontSize: isMobile ? 16 : 18, marginBottom: 16 }}>
              Add New Supplier
            </div>

            {addSupplierError && (
              <div
                style={{
                  background: "#fee2e2",
                  border: "1px solid #fecaca",
                  color: "#dc2626",
                  padding: 12,
                  borderRadius: 6,
                  marginBottom: 16,
                  fontSize: 12,
                }}
              >
                {addSupplierError}
              </div>
            )}

            <div style={{ display: "grid", gap: 12 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Supplier Name *</label>
                <input
                  type="text"
                  value={newSupplier.name}
                  onChange={(e) => setNewSupplier({ ...newSupplier, name: e.target.value })}
                  placeholder="e.g. ABC Supplies Ltd"
                  style={{
                    ...shellStyles.searchInput,
                    marginTop: 6,
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Contact Name</label>
                <input
                  type="text"
                  value={newSupplier.contact_name}
                  onChange={(e) => setNewSupplier({ ...newSupplier, contact_name: e.target.value })}
                  placeholder="Contact person name"
                  style={{
                    ...shellStyles.searchInput,
                    marginTop: 6,
                  }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Phone</label>
                  <input
                    type="tel"
                    value={newSupplier.phone}
                    onChange={(e) => setNewSupplier({ ...newSupplier, phone: e.target.value })}
                    placeholder="Phone number"
                    style={{
                      ...shellStyles.searchInput,
                      marginTop: 6,
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Email</label>
                  <input
                    type="email"
                    value={newSupplier.email}
                    onChange={(e) => setNewSupplier({ ...newSupplier, email: e.target.value })}
                    placeholder="Email address"
                    style={{
                      ...shellStyles.searchInput,
                      marginTop: 6,
                    }}
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Address</label>
                <textarea
                  value={newSupplier.address}
                  onChange={(e) => setNewSupplier({ ...newSupplier, address: e.target.value })}
                  placeholder="Physical address"
                  style={{
                    ...shellStyles.searchInput,
                    marginTop: 6,
                    minHeight: 60,
                    fontFamily: "inherit",
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>KRA PIN</label>
                <input
                  type="text"
                  value={newSupplier.kra_pin}
                  onChange={(e) => setNewSupplier({ ...newSupplier, kra_pin: e.target.value })}
                  placeholder="Tax ID"
                  style={{
                    ...shellStyles.searchInput,
                    marginTop: 6,
                  }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 16 }}>
                <button
                  style={{
                    ...shellStyles.smallButton(false),
                    borderColor: "#cbd5e1",
                    color: "#334155",
                  }}
                  onClick={() => setShowAddSupplier(false)}
                  disabled={addSupplierLoading}
                >
                  Cancel
                </button>
                <button
                  style={{
                    ...shellStyles.smallButton(false),
                    background: "#7c3aed",
                    borderColor: "#7c3aed",
                  }}
                  onClick={handleAddSupplier}
                  disabled={addSupplierLoading}
                >
                  {addSupplierLoading ? "Creating..." : "Create Supplier"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
