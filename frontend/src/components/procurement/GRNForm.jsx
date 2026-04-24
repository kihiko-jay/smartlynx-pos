import { useState, useEffect } from "react";
import { procurementAPI, productsAPI } from "../../api/client";
import { UNIT_TYPES, MONO, BONE, INK, MUTED, BLUE, SAND, SYNE, AMBER, GREEN, RED } from "./styles";
import { Card, Btn, Input, Select, Err, Badge } from "./UIComponents.jsx";
import { fmtKES } from "./styles";

export default function GRNForm({ prefillPoId, onBack, onSaved }) {
  const [suppliers, setSuppliers] = useState([]);
  const [products,  setProducts]  = useState([]);
  const [po,        setPO]        = useState(null);
  const [form, setForm] = useState({
    supplier_id: "", purchase_order_id: prefillPoId || "",
    received_date: new Date().toISOString().slice(0,10), supplier_invoice_number: "",
    supplier_delivery_note: "", notes: "", items: [],
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
  }, []);

  useEffect(() => {
    if (!form.purchase_order_id) { setPO(null); return; }
    procurementAPI.getPO(parseInt(form.purchase_order_id)).then(p => {
      setPO(p);
      setForm(f => ({
        ...f,
        supplier_id: p.supplier_id,
        items: p.items.filter(it => it.remaining_qty_base > 0).map(it => ({
          itemcode:              it.product_id, // Will be converted to itemcode
          product_name:          it.product_name,
          purchase_order_item_id:it.id,
          received_qty_purchase: "0",
          purchase_unit_type:    it.purchase_unit_type,
          units_per_purchase:    it.units_per_purchase,
          damaged_qty_base:      "0",
          rejected_qty_base:     "0",
          cost_per_base_unit:    it.unit_cost,
          batch_number:          "",
          expiry_date:           "",
          notes:                 "",
          _max_base:             it.remaining_qty_base,
        })),
      }));
    }).catch(console.error);
  }, [form.purchase_order_id]);

  // Convert product_id to itemcode when products are loaded
  useEffect(() => {
    if (products.length > 0) {
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
  }, [products]);

  const addItem = () => setForm(f => ({
    ...f, items: [...f.items, {
      itemcode:"", product_name:"", purchase_order_item_id: null,
      received_qty_purchase:"0", purchase_unit_type:"carton",
      units_per_purchase:"24", damaged_qty_base:"0", rejected_qty_base:"0",
      cost_per_base_unit:"0", batch_number:"", expiry_date:"", notes:"", _max_base: null,
    }],
  }));

  const updateItem = (i, field, val) => setForm(f => {
    const items = [...f.items];
    items[i] = { ...items[i], [field]: val };
    if (field === "itemcode") {
      const prod = products.find(p => String(p.itemcode) === String(val));
      if (prod) items[i].product_name = prod.name;
    }
    return { ...f, items };
  });

  const removeItem = (i) => setForm(f => ({ ...f, items: f.items.filter((_,idx)=>idx!==i) }));

  const baseQty      = (it) => Math.ceil((parseFloat(it.received_qty_purchase)||0) * (parseInt(it.units_per_purchase)||1));
  const acceptedQty  = (it) => Math.max(0, baseQty(it) - (parseInt(it.damaged_qty_base)||0) - (parseInt(it.rejected_qty_base)||0));

  const save = async (andPost=false) => {
    if (!form.supplier_id) { setErr("Select a supplier"); return; }
    if (form.items.length === 0) { setErr("Add at least one product"); return; }
    for (const it of form.items) {
      if (!it.itemcode || it.itemcode === "") { setErr("All lines need a product"); return; }
      const dmg = parseInt(it.damaged_qty_base)||0;
      const rej = parseInt(it.rejected_qty_base)||0;
      if (dmg + rej > baseQty(it)) { setErr(`Damaged + rejected cannot exceed received qty for ${it.product_name || "a product"}`); return; }
    }
    setSaving(true); setErr("");
    try {
      const payload = {
        ...form,
        supplier_id:       parseInt(form.supplier_id),
        purchase_order_id: form.purchase_order_id ? parseInt(form.purchase_order_id) : null,
        items: form.items.map(it => ({
          itemcode:               parseInt(it.itemcode),
          purchase_order_item_id: it.purchase_order_item_id || null,
          received_qty_purchase:  parseFloat(it.received_qty_purchase)||0,
          purchase_unit_type:     it.purchase_unit_type,
          units_per_purchase:     parseInt(it.units_per_purchase)||1,
          damaged_qty_base:       parseInt(it.damaged_qty_base)||0,
          rejected_qty_base:      parseInt(it.rejected_qty_base)||0,
          cost_per_base_unit:     parseFloat(it.cost_per_base_unit)||0,
          batch_number:           it.batch_number || undefined,
          expiry_date:            it.expiry_date  || undefined,
          notes:                  it.notes        || undefined,
        })),
      };
      const grn = await procurementAPI.createGRN(payload);
      if (andPost) await procurementAPI.postGRN(grn.id);
      onSaved(grn.id);
    } catch(e) {
      setErr(e?.detail || e?.message || "Failed to save GRN");
    } finally { setSaving(false); }
  };

  return (
    <div>
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:24 }}>
        <Btn variant="secondary" onClick={onBack}>← Back</Btn>
        <span style={{ fontFamily:SYNE, fontWeight:800, fontSize:20 }}>Receive Inventory</span>
      </div>
      <Err msg={err}/>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16, marginBottom:20 }}>
        <Card>
          <div style={{ fontWeight:700, fontFamily:MONO, fontSize:13, marginBottom:16 }}>Receiving Details</div>
          <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
            <Select label="Supplier *" value={form.supplier_id}
                    onChange={e => setForm(f=>({...f,supplier_id:e.target.value}))}>
              <option value="">— select supplier —</option>
              {suppliers.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
            <Input label="Received Date" type="date" value={form.received_date}
                   onChange={e => setForm(f=>({...f,received_date:e.target.value}))}/>
            <Input label="Supplier Invoice No." value={form.supplier_invoice_number}
                   onChange={e => setForm(f=>({...f,supplier_invoice_number:e.target.value}))}/>
            <Input label="Delivery Note No." value={form.supplier_delivery_note}
                   onChange={e => setForm(f=>({...f,supplier_delivery_note:e.target.value}))}/>
          </div>
        </Card>
        <Card>
          <div style={{ fontWeight:700, fontFamily:MONO, fontSize:13, marginBottom:16 }}>Link Purchase Order (optional)</div>
          <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
            <Input label="PO ID (leave blank for direct receive)"
                   type="number" value={form.purchase_order_id}
                   onChange={e => setForm(f=>({...f,purchase_order_id:e.target.value}))}/>
            {po && (
              <div style={{ background:"#f5f1e8", borderRadius:6, padding:"10px 12px", fontSize:12, fontFamily:MONO }}>
                <span style={{ color:MUTED }}>Linked: </span>
                <strong>{po.po_number}</strong> — {po.supplier_name}
              </div>
            )}
            <Input label="Notes" value={form.notes}
                   onChange={e => setForm(f=>({...f,notes:e.target.value}))}/>
          </div>
        </Card>
      </div>

      <Card style={{ marginBottom:20 }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16 }}>
          <div style={{ fontWeight:700, fontFamily:MONO, fontSize:13 }}>Products to Receive</div>
          <Btn small onClick={addItem}>+ Add Line</Btn>
        </div>
        {form.items.length === 0 ? (
          <div style={{ textAlign:"center", color:MUTED, padding:32, fontFamily:MONO, fontSize:12 }}>
            {po ? "All remaining PO items are added above." : "Click '+ Add Line' to add products."}
          </div>
        ) : (
          <div style={{ overflowX:"auto" }}>
            <table style={{ width:"100%", borderCollapse:"collapse", minWidth:900 }}>
              <thead>
                <tr style={{ background:"#f5f1e8" }}>
                  {["Product","Received","Unit Type","Units/Pkg","Base Units","Damaged","Rejected","Accepted","Cost/Unit","Batch","Expiry",""].map(h=>(
                    <th key={h} style={{ padding:"8px 8px", textAlign:"left", fontSize:10,
                                         fontFamily:MONO, color:MUTED, fontWeight:600,
                                         textTransform:"uppercase", letterSpacing:"0.06em",
                                         borderBottom:`1px solid ${BONE}`, whiteSpace:"nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {form.items.map((item, i) => {
                  const accepted = acceptedQty(item);
                  const base     = baseQty(item);
                  return (
                    <tr key={i} style={{ borderBottom:`1px solid ${BONE}` }}>
                      <td style={{ padding:"6px 8px", minWidth:140 }}>
                        {item.purchase_order_item_id ? (
                          <span style={{ fontFamily:MONO, fontSize:12, fontWeight:600 }}>{item.product_name}</span>
                        ) : (
                          <select value={item.itemcode}
                                  onChange={e => updateItem(i,"itemcode",e.target.value)}
                                  style={{ padding:"5px 7px", borderRadius:6, border:`1px solid ${BONE}`,
                                           fontFamily:MONO, fontSize:11, width:140 }}>
                            <option value="">— product —</option>
                            {products.map(p=><option key={p.id} value={p.itemcode}>{p.name}</option>)}
                          </select>
                        )}
                      </td>
                      <td style={{ padding:"6px 8px", width:70 }}>
                        <input type="number" min="0" step="0.001" value={item.received_qty_purchase}
                               onChange={e => updateItem(i,"received_qty_purchase",e.target.value)}
                               style={{ padding:"5px 6px", borderRadius:6, border:`1px solid ${BONE}`,
                                        fontFamily:MONO, fontSize:11, width:70 }}/>
                      </td>
                      <td style={{ padding:"6px 8px", width:90 }}>
                        <select value={item.purchase_unit_type}
                                onChange={e => updateItem(i,"purchase_unit_type",e.target.value)}
                                style={{ padding:"5px 6px", borderRadius:6, border:`1px solid ${BONE}`,
                                         fontFamily:MONO, fontSize:11 }}>
                          {UNIT_TYPES.map(u=><option key={u} value={u}>{u}</option>)}
                        </select>
                      </td>
                      <td style={{ padding:"6px 8px", width:60 }}>
                        <input type="number" min="1" step="1" value={item.units_per_purchase}
                               onChange={e => updateItem(i,"units_per_purchase",e.target.value)}
                               style={{ padding:"5px 6px", borderRadius:6, border:`1px solid ${BONE}`,
                                        fontFamily:MONO, fontSize:11, width:60 }}/>
                      </td>
                      <td style={{ padding:"6px 8px", fontFamily:MONO, fontSize:12, fontWeight:600, color:BLUE, textAlign:"center" }}>
                        {base.toLocaleString()}
                      </td>
                      <td style={{ padding:"6px 8px", width:70 }}>
                        <input type="number" min="0" step="1" value={item.damaged_qty_base}
                               onChange={e => updateItem(i,"damaged_qty_base",e.target.value)}
                               style={{ padding:"5px 6px", borderRadius:6, border:`1px solid ${AMBER}`,
                                        fontFamily:MONO, fontSize:11, width:70, background:"#fffbeb" }}/>
                      </td>
                      <td style={{ padding:"6px 8px", width:70 }}>
                        <input type="number" min="0" step="1" value={item.rejected_qty_base}
                               onChange={e => updateItem(i,"rejected_qty_base",e.target.value)}
                               style={{ padding:"5px 6px", borderRadius:6, border:`1px solid #fca5a5`,
                                        fontFamily:MONO, fontSize:11, width:70, background:"#fef2f2" }}/>
                      </td>
                      <td style={{ padding:"6px 8px", fontFamily:MONO, fontSize:13, fontWeight:700,
                                   color: accepted>0 ? GREEN : RED, textAlign:"center" }}>
                        {accepted.toLocaleString()}
                      </td>
                      <td style={{ padding:"6px 8px", width:80 }}>
                        <input type="number" min="0" step="0.01" value={item.cost_per_base_unit}
                               onChange={e => updateItem(i,"cost_per_base_unit",e.target.value)}
                               style={{ padding:"5px 6px", borderRadius:6, border:`1px solid ${BONE}`,
                                        fontFamily:MONO, fontSize:11, width:80 }}/>
                      </td>
                      <td style={{ padding:"6px 8px", width:90 }}>
                        <input placeholder="batch" value={item.batch_number}
                               onChange={e => updateItem(i,"batch_number",e.target.value)}
                               style={{ padding:"5px 6px", borderRadius:6, border:`1px solid ${BONE}`,
                                        fontFamily:MONO, fontSize:11, width:90 }}/>
                      </td>
                      <td style={{ padding:"6px 8px", width:100 }}>
                        <input type="date" value={item.expiry_date}
                               onChange={e => updateItem(i,"expiry_date",e.target.value)}
                               style={{ padding:"5px 6px", borderRadius:6, border:`1px solid ${BONE}`,
                                        fontFamily:MONO, fontSize:11, width:100 }}/>
                      </td>
                      <td style={{ padding:"6px 8px" }}>
                        {!item.purchase_order_item_id &&
                          <Btn small variant="danger" onClick={() => removeItem(i)}>✕</Btn>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div style={{ background:"#fff", border:`1px solid ${BONE}`, borderRadius:10,
                    padding:"14px 24px", marginBottom:20 }}>
        <div style={{ fontFamily:MONO, fontSize:11, color:MUTED, marginBottom:4 }}>RECEIVING SUMMARY</div>
        <div style={{ display:"flex", gap:32, flexWrap:"wrap" }}>
          <span style={{ fontFamily:MONO, fontSize:13 }}>
            Total received: <strong>{form.items.reduce((s,it) => s + baseQty(it), 0).toLocaleString()}</strong>
          </span>
          <span style={{ fontFamily:MONO, fontSize:13, color:GREEN }}>
            Accepted: <strong>{form.items.reduce((s,it) => s + acceptedQty(it), 0).toLocaleString()}</strong>
          </span>
          <span style={{ fontFamily:MONO, fontSize:13, color:AMBER }}>
            Damaged: <strong>{form.items.reduce((s,it) => s + (parseInt(it.damaged_qty_base)||0), 0).toLocaleString()}</strong>
          </span>
          <span style={{ fontFamily:MONO, fontSize:13, color:RED }}>
            Rejected: <strong>{form.items.reduce((s,it) => s + (parseInt(it.rejected_qty_base)||0), 0).toLocaleString()}</strong>
          </span>
        </div>
      </div>

      <div style={{ display:"flex", gap:12, justifyContent:"flex-end" }}>
        <Btn variant="secondary" onClick={onBack}>Cancel</Btn>
        <Btn variant="secondary" onClick={() => save(false)} disabled={saving}>Save Draft</Btn>
        <Btn variant="success"   onClick={() => save(true)}  disabled={saving}>
          {saving ? "Posting…" : "Post GRN"}
        </Btn>
      </div>
    </div>
  );
}
