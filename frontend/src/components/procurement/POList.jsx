import { useState, useEffect, useCallback } from "react";
import { procurementAPI } from "../../api/client";
import { MONO, BONE, INK, MUTED, BLUE, SAND, fmtKES } from "./styles";
import { Badge, Btn, Card, SectionHead, Loading } from "./UIComponents.jsx";

export default function POList({ onNew, onView }) {
  const [pos, setPOs]   = useState([]);
  const [loading, setL] = useState(true);
  const [filter, setF]  = useState("all");

  const load = useCallback(() => {
    setL(true);
    const p = filter !== "all" ? { status: filter } : {};
    procurementAPI.listPOs(p)
      .then(setPOs).catch(console.error).finally(() => setL(false));
  }, [filter]);

  useEffect(load, [load]);

  if (loading) return <Loading/>;

  return (
    <div>
      <SectionHead title="Purchase Orders" sub={`${pos.length} orders`}
        action={<Btn onClick={onNew}>+ New PO</Btn>}/>

      <div style={{ display:"flex", gap:8, marginBottom:16 }}>
        {["all","draft","submitted","approved","partially_received","fully_received","cancelled"].map(s => (
          <button key={s} onClick={() => setF(s)}
            style={{ padding:"4px 12px", borderRadius:20, border:`1px solid ${BONE}`,
                     background: filter===s ? INK : "#fff",
                     color: filter===s ? "#fff" : INK,
                     fontFamily:MONO, fontSize:11, cursor:"pointer" }}>
            {s === "all" ? "All" : s.replace(/_/g," ")}
          </button>
        ))}
      </div>

      {pos.length === 0 ? (
        <Card><div style={{ textAlign:"center", color:MUTED, padding:40, fontFamily:MONO }}>No purchase orders yet. Create one to start ordering stock.</div></Card>
      ) : (
        <Card style={{ padding:0 }}>
          <table style={{ width:"100%", borderCollapse:"collapse" }}>
            <thead>
              <tr style={{ background:SAND }}>
                {["PO Number","Supplier","Order Date","Expected","Items","Total","Status",""].map(h => (
                  <th key={h} style={{ padding:"10px 14px", textAlign:"left", fontSize:10,
                                       fontFamily:MONO, color:MUTED, fontWeight:600,
                                       textTransform:"uppercase", letterSpacing:"0.06em",
                                       borderBottom:`1px solid ${BONE}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pos.map((po, i) => (
                <tr key={po.id} style={{ borderBottom: i<pos.length-1 ? `1px solid ${BONE}` : "none" }}>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:12,
                               fontWeight:600, color:BLUE, cursor:"pointer" }}
                      onClick={() => onView(po.id)}>
                    {po.po_number}
                  </td>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:12 }}>{po.supplier_name}</td>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:11, color:MUTED }}>{po.order_date}</td>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:11, color:MUTED }}>{po.expected_date || "—"}</td>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:12 }}>{po.item_count}</td>
                  <td style={{ padding:"10px 14px", fontFamily:MONO, fontSize:12, fontWeight:600 }}>{fmtKES(po.total_amount)}</td>
                  <td style={{ padding:"10px 14px" }}><Badge status={po.status}/></td>
                  <td style={{ padding:"10px 14px" }}>
                    <Btn small variant="secondary" onClick={() => onView(po.id)}>View</Btn>
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
