import { useState, useEffect } from "react";
import { procurementAPI } from "../../api/client";
import { MONO, BONE, INK, MUTED, BLUE, SAND, SYNE, AMBER, GREEN, RED } from "./styles";
import { Badge, Btn, Card, Err, Loading, SectionHead } from "./UIComponents.jsx";
import { fmtKES } from "./styles";

export default function POView({ poId, onBack, onCreateGRN }) {
  const [po,      setPO]   = useState(null);
  const [loading, setL]    = useState(true);
  const [acting,  setActing] = useState("");
  const [err,     setErr]  = useState("");
  const [showEmailModal, setShowEmailModal] = useState(false);

  useEffect(() => {
    setL(true);
    procurementAPI.getPO(poId).then(setPO).catch(console.error).finally(() => setL(false));
  }, [poId]);

  const action = async (fn, label) => {
    setActing(label); setErr("");
    try { const r = await fn(); setPO(r); }
    catch(e) { setErr(e?.detail || e?.message || `${label} failed`); }
    finally   { setActing(""); }
  };

  const downloadPDF = async (po, mode) => {
  try {
    setErr("");

    const result = await procurementAPI.downloadPOPdf(
      po.id,
      mode === "download"
    );

    if (!result?.blob) {
      throw new Error("No PDF data returned");
    }

    const blobUrl = URL.createObjectURL(result.blob);

    if (mode === "download") {
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `PO-${po.po_number}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();

      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } else {
      const win = window.open(blobUrl, "_blank", "noopener,noreferrer");
      if (!win) {
        setErr("Popup blocked. Please allow popups to preview/print the PDF.");
      }
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    }
  } catch (e) {
    setErr(`Failed to generate PDF: ${e?.message || e}`);
  }
};

  if (loading) return <Loading/>;
  if (!po)     return <div style={{ color:RED, fontFamily:MONO }}>PO not found</div>;

  const canSubmit  = po.status === "draft";
  const canApprove = po.status === "submitted";
  const canReceive = ["approved","partially_received"].includes(po.status);
  const canCancel  = !["fully_received","closed","cancelled"].includes(po.status);

  return (
    <div>
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:24 }}>
        <Btn variant="secondary" onClick={onBack}>← Back</Btn>
        <span style={{ fontFamily:SYNE, fontWeight:800, fontSize:20 }}>
          {po.po_number}
        </span>
        <Badge status={po.status}/>
      </div>
      <Err msg={err}/>

      <div style={{ display:"flex", gap:8, marginBottom:20, flexWrap:"wrap" }}>
        {canSubmit  && <Btn onClick={() => action(() => procurementAPI.submitPO(po.id),  "Submit")}  disabled={!!acting}>{acting==="Submit" ?"Submitting…" :"Submit PO"}</Btn>}
        {canApprove && <Btn variant="success" onClick={() => action(() => procurementAPI.approvePO(po.id), "Approve")} disabled={!!acting}>{acting==="Approve"?"Approving…" :"Approve PO"}</Btn>}
        {canReceive && <Btn variant="success" onClick={() => onCreateGRN(po.id)}>Receive Stock →</Btn>}
        {canCancel  && <Btn variant="danger"  onClick={() => action(() => procurementAPI.cancelPO(po.id),  "Cancel")}  disabled={!!acting}>{acting==="Cancel" ?"Cancelling…":"Cancel PO"}</Btn>}
        <Btn variant="secondary" onClick={() => downloadPDF(po, "download")}>⬇ Download PDF</Btn>
        <Btn variant="secondary" onClick={() => downloadPDF(po, "print")}>🖨 Print</Btn>
        {po.status !== "draft" && <Btn variant="secondary" onClick={() => setShowEmailModal(true)}>✉ Email to Supplier</Btn>}
      </div>

      {showEmailModal && (
        <EmailModal
          po={po}
          onClose={() => setShowEmailModal(false)}
          onSent={() => { setShowEmailModal(false); setErr(""); }}
          onError={(e) => setErr(e)}
        />
      )}

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:16, marginBottom:20 }}>
        {[
          ["Supplier",  po.supplier_name],
          ["Order Date",po.order_date],
          ["Expected",  po.expected_date || "Not set"],
          ["Currency",  po.currency],
          ["Subtotal",  fmtKES(po.subtotal)],
          ["Total",     fmtKES(po.total_amount)],
        ].map(([k,v]) => (
          <Card key={k} style={{ padding:"14px 18px" }}>
            <div style={{ fontSize:10, color:MUTED, fontFamily:MONO, textTransform:"uppercase",
                          letterSpacing:"0.06em", marginBottom:6 }}>{k}</div>
            <div style={{ fontFamily:MONO, fontWeight:600, fontSize:14 }}>{v}</div>
          </Card>
        ))}
      </div>

      {po.notes && (
        <Card style={{ marginBottom:16, padding:"12px 18px" }}>
          <span style={{ fontSize:11, color:MUTED, fontFamily:MONO }}>Notes: </span>
          <span style={{ fontFamily:MONO, fontSize:12 }}>{po.notes}</span>
        </Card>
      )}

      <Card style={{ padding:0 }}>
        <table style={{ width:"100%", borderCollapse:"collapse" }}>
          <thead>
            <tr style={{ background:SAND }}>
              {["Product","SKU","Ordered","Unit Type","UPP","Ordered (base)","Received","Remaining","Unit Cost","Line Total"].map(h=>(
                <th key={h} style={{ padding:"10px 12px", textAlign:"left", fontSize:10,
                                     fontFamily:MONO, color:MUTED, fontWeight:600,
                                     textTransform:"uppercase", letterSpacing:"0.06em",
                                     borderBottom:`1px solid ${BONE}` }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {po.items.map((item, i) => {
              const pct = item.ordered_qty_base > 0
                ? Math.round((item.received_qty_base / item.ordered_qty_base) * 100) : 0;
              return (
                <tr key={item.id} style={{ borderBottom: i<po.items.length-1?`1px solid ${BONE}`:"none" }}>
                  <td style={{ padding:"10px 12px", fontFamily:MONO, fontSize:12, fontWeight:600 }}>{item.product_name}</td>
                  <td style={{ padding:"10px 12px", fontFamily:MONO, fontSize:11, color:MUTED }}>{item.product_sku}</td>
                  <td style={{ padding:"10px 12px", fontFamily:MONO, fontSize:12 }}>{item.ordered_qty_purchase}</td>
                  <td style={{ padding:"10px 12px", fontFamily:MONO, fontSize:11 }}>{item.purchase_unit_type}</td>
                  <td style={{ padding:"10px 12px", fontFamily:MONO, fontSize:11 }}>{item.units_per_purchase}</td>
                  <td style={{ padding:"10px 12px", fontFamily:MONO, fontSize:12, fontWeight:600 }}>{item.ordered_qty_base.toLocaleString()}</td>
                  <td style={{ padding:"10px 12px" }}>
                    <div style={{ fontFamily:MONO, fontSize:12, fontWeight:600,
                                  color: pct>=100 ? GREEN : pct>0 ? AMBER : MUTED }}>
                      {item.received_qty_base.toLocaleString()}
                      <span style={{ fontSize:10, color:MUTED, marginLeft:4 }}>({pct}%)</span>
                    </div>
                  </td>
                  <td style={{ padding:"10px 12px", fontFamily:MONO, fontSize:12,
                               color: item.remaining_qty_base > 0 ? AMBER : GREEN }}>
                    {item.remaining_qty_base.toLocaleString()}
                  </td>
                  <td style={{ padding:"10px 12px", fontFamily:MONO, fontSize:12 }}>{fmtKES(item.unit_cost)}</td>
                  <td style={{ padding:"10px 12px", fontFamily:MONO, fontSize:12, fontWeight:600 }}>{fmtKES(item.line_total)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function EmailModal({ po, onClose, onSent, onError }) {
  const [email, setEmail] = useState(po.supplier?.email || "");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);

 const handleSend = async () => {
  if (!email) {
    onError("Please enter an email address");
    return;
  }

  setSending(true);
  try {
    await procurementAPI.sendPOEmail(po.id, {
      recipient_email: email,
      message,
    });
    onSent();
  } catch (e) {
    onError(e?.message || "Failed to send email");
  } finally {
    setSending(false);
  }
};

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <Card style={{ padding: 24, maxWidth: 400, borderRadius: 8 }}>
        <h3 style={{ marginTop: 0, marginBottom: 16, fontFamily: SYNE }}>Email PO {po.po_number}</h3>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: "block", fontSize: 12, fontFamily: MONO, marginBottom: 6 }}>To:</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="supplier@example.com"
            style={{ width: "100%", padding: 8, fontFamily: MONO, border: `1px solid ${BONE}`, borderRadius: 4, boxSizing: "border-box" }}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: "block", fontSize: 12, fontFamily: MONO, marginBottom: 6 }}>Message (optional):</label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Add a custom message..."
            style={{ width: "100%", padding: 8, fontFamily: MONO, border: `1px solid ${BONE}`, borderRadius: 4, minHeight: 80, boxSizing: "border-box" }}
          />
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Btn variant="secondary" onClick={onClose} disabled={sending}>Cancel</Btn>
          <Btn variant="success" onClick={handleSend} disabled={sending}>{sending ? "Sending…" : "Send Email"}</Btn>
        </div>
      </Card>
    </div>
  );
}
