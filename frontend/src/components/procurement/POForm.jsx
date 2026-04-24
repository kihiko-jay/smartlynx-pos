import { useState, useEffect } from "react";
import { procurementAPI, productsAPI } from "../../api/client";
import { UNIT_TYPES, MONO, BONE, INK, MUTED, BLUE, SAND, SYNE } from "./styles";
import { Card, Btn, Input, Select, Err } from "./UIComponents.jsx";
import { fmtKES } from "./styles";

export default function POForm({ poId, onBack, onSaved }) {
  const isEdit = !!poId;
  const [suppliers, setSuppliers] = useState([]);
  const [products,  setProducts]  = useState([]);
  const [form, setForm] = useState({
    supplier_id: "", expected_date: "", notes: "", currency: "KES", items: [],
  });
  const [saving, setSaving] = useState(false);
  const [err,    setErr]    = useState("");

  useEffect(() => {
    productsAPI.suppliers().then(r => {
      const list = Array.isArray(r) ? r : (r?.items || r?.suppliers || r?.data || []);
      setSuppliers(Array.isArray(list) ? list : []);
    }).catch(e => {
      console.error("Failed to load suppliers:", e.message);
      setSuppliers([]);
    });
    
    productsAPI.list({ limit:200 }).then(r => {
      const list = Array.isArray(r) ? r : (r?.items || r?.products || r?.data || []);
      setProducts(Array.isArray(list) ? list : []);
    }).catch(e => {
      console.error("Failed to load products:", e.message);
      setProducts([]);
    });

    if (isEdit) {
      procurementAPI.getPO(poId).then(po => {
        setForm({
          supplier_id:   po.supplier_id,
          expected_date: po.expected_date || "",
          notes:         po.notes || "",
          currency:      po.currency,
          items: po.items.map(it => ({
            itemcode:               it.product_id, // Temporary, will be converted to itemcode
            ordered_qty_purchase: it.ordered_qty_purchase,
            purchase_unit_type:   it.purchase_unit_type,
            units_per_purchase:   it.units_per_purchase,
            unit_cost:            it.unit_cost,
            notes:                it.notes || "",
          })),
        });
      }).catch(console.error);
    }
  }, [isEdit, poId]);

  // Convert product_id to itemcode when products are loaded
  useEffect(() => {
    if (isEdit && products.length > 0) {
      setForm(f => ({
        ...f,
        items: f.items.map(it => {
          // If itemcode is a number, it's actually a product_id that needs conversion
          if (typeof it.itemcode === 'number' || (typeof it.itemcode === 'string' && !isNaN(it.itemcode))) {
            const prod = products.find(p => p.id === parseInt(it.itemcode));
            return { ...it, itemcode: prod?.itemcode?.toString() || it.itemcode };
          }
          return it;
        })
      }));
    }
  }, [products, isEdit]);

  const addItem = () => setForm(f => ({
    ...f, items: [...f.items, {
      itemcode:"", ordered_qty_purchase:"1", purchase_unit_type:"carton",
      units_per_purchase:"24", unit_cost:"0", notes:"",
    }],
  }));

  const removeItem = (i) => setForm(f => ({ ...f, items: f.items.filter((_,idx) => idx!==i) }));

  const updateItem = (i, field, val) => setForm(f => {
    const items = [...f.items];
    items[i] = { ...items[i], [field]: val };
    return { ...f, items };
  });

  const baseUnits = (item) => {
    const qty = parseFloat(item.ordered_qty_purchase) || 0;
    const upu = parseInt(item.units_per_purchase)     || 1;
    return Math.ceil(qty * upu);
  };

  const lineTotal = (item) => {
    return (baseUnits(item) * (parseFloat(item.unit_cost) || 0)).toFixed(2);
  };

  const grandTotal = () => form.items.reduce((s, it) => s + parseFloat(lineTotal(it)), 0).toFixed(2);

  const save = async () => {
    if (!form.supplier_id) { setErr("Select a supplier"); return; }
    if (form.items.length === 0) { setErr("Add at least one product"); return; }
    for (const it of form.items) {
      if (!it.itemcode || it.itemcode === "") { setErr("All items need a product"); return; }
      if (parseFloat(it.ordered_qty_purchase) <= 0) { setErr("Quantity must be > 0"); return; }
    }
    setSaving(true); setErr("");
    try {
      const payload = {
        ...form,
        supplier_id: parseInt(form.supplier_id),
        items: form.items.map(it => ({
          itemcode:               parseInt(it.itemcode),
          ordered_qty_purchase: parseFloat(it.ordered_qty_purchase),
          purchase_unit_type:   it.purchase_unit_type,
          units_per_purchase:   parseInt(it.units_per_purchase),
          unit_cost:            parseFloat(it.unit_cost),
          notes:                it.notes || undefined,
        })),
      };
      const result = isEdit
        ? await procurementAPI.updatePO(poId, payload)
        : await procurementAPI.createPO(payload);
      onSaved(result.id || poId);
    } catch(e) {
      setErr(e?.detail || e?.message || "Save failed");
    } finally { setSaving(false); }
  };

  return (
    <div>
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:24 }}>
        <Btn variant="secondary" onClick={onBack}>← Back</Btn>
        <span style={{ fontFamily:SYNE, fontWeight:800, fontSize:20 }}>
          {isEdit ? "Edit Purchase Order" : "New Purchase Order"}
        </span>
      </div>
      <Err msg={err}/>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16, marginBottom:20 }}>
        <Card>
          <div style={{ fontWeight:700, fontFamily:MONO, fontSize:13, marginBottom:16 }}>Order Details</div>
          <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
            <Select label="Supplier *" value={form.supplier_id}
                    onChange={e => setForm(f=>({...f,supplier_id:e.target.value}))}>
              <option value="">— select supplier —</option>
              {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
            <Input label="Expected Delivery Date" type="date" value={form.expected_date}
                   onChange={e => setForm(f=>({...f,expected_date:e.target.value}))}/>
            <Input label="Notes" value={form.notes}
                   onChange={e => setForm(f=>({...f,notes:e.target.value}))}/>
          </div>
        </Card>
        <Card style={{ display:"flex", flexDirection:"column", justifyContent:"center", alignItems:"center", gap:8 }}>
          <div style={{ fontSize:11, color:MUTED, fontFamily:MONO }}>ORDER TOTAL</div>
          <div style={{ fontFamily:SYNE, fontWeight:800, fontSize:32, color:INK }}>{fmtKES(grandTotal())}</div>
          <div style={{ fontSize:11, color:MUTED, fontFamily:MONO }}>{form.items.length} line item{form.items.length!==1?"s":""}</div>
        </Card>
      </div>

      <Card>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16 }}>
          <div style={{ fontWeight:700, fontFamily:MONO, fontSize:13 }}>Order Lines</div>
          <Btn small onClick={addItem}>+ Add Product</Btn>
        </div>

        {form.items.length === 0 ? (
          <div style={{ textAlign:"center", color:MUTED, padding:32, fontFamily:MONO, fontSize:12 }}>
            No items yet. Click "+ Add Product" to start.
          </div>
        ) : (
          <table style={{ width:"100%", borderCollapse:"collapse" }}>
            <thead>
              <tr style={{ background:SAND }}>
                {["Product","Qty (Purchase Units)","Unit Type","Units/Purchase","Cost/Unit","Base Units","Line Total",""].map(h=>(
                  <th key={h} style={{ padding:"8px 10px", textAlign:"left", fontSize:10,
                                       fontFamily:MONO, color:MUTED, letterSpacing:"0.06em",
                                       textTransform:"uppercase", fontWeight:600,
                                       borderBottom:`1px solid ${BONE}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {form.items.map((item, i) => (
                <tr key={i} style={{ borderBottom:`1px solid ${BONE}` }}>
                  <td style={{ padding:"8px 10px", minWidth:160 }}>
                    <select value={item.itemcode}
                            onChange={e => updateItem(i,"itemcode",e.target.value)}
                            style={{ padding:"6px 8px", borderRadius:6, border:`1px solid ${BONE}`,
                                     fontFamily:MONO, fontSize:11, width:"100%" }}>
                      <option value="">— product —</option>
                      {products.map(p=><option key={p.id} value={p.itemcode}>{p.name} ({p.sku})</option>)}
                    </select>
                  </td>
                  <td style={{ padding:"8px 10px", width:90 }}>
                    <input type="number" min="0.001" step="0.001"
                           value={item.ordered_qty_purchase}
                           onChange={e => updateItem(i,"ordered_qty_purchase",e.target.value)}
                           style={{ padding:"6px 8px", borderRadius:6, border:`1px solid ${BONE}`,
                                    fontFamily:MONO, fontSize:11, width:"100%" }}/>
                  </td>
                  <td style={{ padding:"8px 10px", width:100 }}>
                    <select value={item.purchase_unit_type}
                            onChange={e => updateItem(i,"purchase_unit_type",e.target.value)}
                            style={{ padding:"6px 8px", borderRadius:6, border:`1px solid ${BONE}`,
                                     fontFamily:MONO, fontSize:11, width:"100%" }}>
                      {UNIT_TYPES.map(u=><option key={u} value={u}>{u}</option>)}
                    </select>
                  </td>
                  <td style={{ padding:"8px 10px", width:80 }}>
                    <input type="number" min="1" step="1"
                           value={item.units_per_purchase}
                           onChange={e => updateItem(i,"units_per_purchase",e.target.value)}
                           style={{ padding:"6px 8px", borderRadius:6, border:`1px solid ${BONE}`,
                                    fontFamily:MONO, fontSize:11, width:"100%" }}/>
                  </td>
                  <td style={{ padding:"8px 10px", width:100 }}>
                    <input type="number" min="0" step="0.01"
                           value={item.unit_cost}
                           onChange={e => updateItem(i,"unit_cost",e.target.value)}
                           style={{ padding:"6px 8px", borderRadius:6, border:`1px solid ${BONE}`,
                                    fontFamily:MONO, fontSize:11, width:"100%" }}/>
                  </td>
                  <td style={{ padding:"8px 10px", fontFamily:MONO, fontSize:12,
                               fontWeight:600, color:BLUE }}>
                    {baseUnits(item).toLocaleString()}
                  </td>
                  <td style={{ padding:"8px 10px", fontFamily:MONO, fontSize:12, fontWeight:600 }}>
                    {fmtKES(lineTotal(item))}
                  </td>
                  <td style={{ padding:"8px 10px" }}>
                    <Btn small variant="danger" onClick={() => removeItem(i)}>✕</Btn>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <div style={{ display:"flex", gap:12, marginTop:20, justifyContent:"flex-end" }}>
        <Btn variant="secondary" onClick={onBack}>Cancel</Btn>
        <Btn onClick={save} disabled={saving}>{saving ? "Saving…" : isEdit ? "Save Changes" : "Create PO"}</Btn>
      </div>
    </div>
  );
}
