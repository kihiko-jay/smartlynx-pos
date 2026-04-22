import { useState, useEffect } from "react";
import { procurementAPI, productsAPI } from "../../api/client";
import { UNIT_TYPES, MONO, BONE, INK, MUTED, BLUE, SAND, SYNE } from "./styles";
import { Card, Btn, Input, Select, Err, Badge } from "./UIComponents.jsx";
import { fmtKES } from "./styles";

export default function GRNList({ onNew, onView }) {
  const [grns,    setGRNs] = useState([]);
  const [loading, setL]    = useState(true);

  useEffect(() => {
    procurementAPI.listGRNs({})
      .then(setGRNs).catch(console.error).finally(() => setL(false));
  }, []);

  if (loading) return <div style={{ textAlign:"center", padding:60 }}>Loading…</div>;

  return (
    <div>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:20 }}>
        <div>
          <div style={{ fontFamily:SYNE, fontWeight:800, fontSize:20 }}>Goods Received Notes</div>
          <div style={{ fontSize:11, color:MUTED, marginTop:3, fontFamily:MONO }}>{grns.length} records</div>
        </div>
        <Btn onClick={() => onNew(null)}>+ Receive Stock</Btn>
      </div>

      {grns.length === 0 ? (
        <Card><div style={{ textAlign:"center", color:MUTED, padding:40, fontFamily:MONO }}>No GRNs yet. Receive stock against an approved PO or directly.</div></Card>
      ) : (
        <Card style={{ padding:0 }}>
          <table style={{ width:"100%", borderCollapse:"collapse" }}>
            <thead>
              <tr style={{ background:SAND }}>
                {["GRN Number","Supplier","Linked PO","Received Date","Items","Status",""].map(h=>(
                  <th key={h} style={{ padding:"10px 14px", textAlign:"left", fontSize:10,
                                       fontFamily:MONO, color:MUTED, fontWeight:600,
                                       textTransform:"uppercase", letterSpacing:"0.06em",
                                       borderBottom:`1px solid ${BONE}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grns.map((grn,i) => (
                <tr key={grn.id} style={{ borderBottom: i<grns.length-1?`1px solid ${BONE}`:"none" }}>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:12,
                               fontWeight:600, color:BLUE, cursor:"pointer" }}
                      onClick={() => onView(grn.id)}>{grn.grn_number}</td>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:12 }}>{grn.supplier_name}</td>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:11, color:MUTED }}>{grn.po_number || "—"}</td>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:11, color:MUTED }}>{grn.received_date}</td>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:12 }}>{grn.item_count}</td>
                  <td style={{ padding:"10px 14px" }}><Badge status={grn.status}/></td>
                  <td style={{ padding:"10px 14px" }}>
                    <Btn small variant="secondary" onClick={() => onView(grn.id)}>View</Btn>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
