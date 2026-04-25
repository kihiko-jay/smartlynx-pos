import { useState, useEffect, useCallback } from "react";
import { procurementAPI, getToken } from "../../api/client";
import { MONO, SYNE, SAND, BONE, MUTED, AMBER, GREEN, RED, fmtKES } from "./styles";
import { Card, Btn, Badge, Err, Loading } from "./UIComponents";

export default function GRNView({ grnId, onBack }) {
  const [grn, setGRN] = useState(null);
  const [loading, setLoading] = useState(true);
  const [acting, setA] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    setLoading(true);
    procurementAPI
      .getGRN(grnId)
      .then(setGRN)
      .catch((e) => setErr(e?.detail || e?.message || "Load failed"))
      .finally(() => setLoading(false));
  }, [grnId]);

  const post = async () => {
    setA(true);
    setErr("");
    try {
      const r = await procurementAPI.postGRN(grnId);
      setGRN(r);
    } catch (e) {
      setErr(e?.detail || e?.message || "Post failed");
    } finally {
      setA(false);
    }
  };

  const downloadGRNPDF = async (grn, mode) => {
    try {
      const token = getToken();
      if (!token) {
        setErr("Authentication required. Please log in again.");
        return;
      }
      
      const url = `/api/v1/procurement/grns/${grn.id}/pdf?download=${mode === "download"}`;
      const response = await fetch(url, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to generate PDF: ${response.status} ${response.statusText}`);
      }

      const blob = await response.blob();
      
      if (mode === "download") {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `GRN-${grn.grn_number}.pdf`;
        a.click();
        URL.revokeObjectURL(a.href);
      } else {
        const pdfUrl = URL.createObjectURL(blob);
        window.open(pdfUrl, "_blank");
      }
    } catch(e) {
      setErr(`Failed to generate PDF: ${e?.message || e}`);
    }
  };

  if (loading) return <Loading />;
  if (!grn)
    return (
      <div style={{ color: RED, fontFamily: MONO }}>GRN not found</div>
    );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <Btn variant="secondary" onClick={onBack}>
          ← Back
        </Btn>
        <span style={{ fontFamily: SYNE, fontWeight: 800, fontSize: 20 }}>
          {grn.grn_number}
        </span>
        <Badge status={grn.status} />
      </div>
      <Err msg={err} />

      <div style={{ marginBottom: 16, display: "flex", gap: 8 }}>
        {grn.status === "draft" && (
          <Btn variant="success" onClick={post} disabled={acting}>
            {acting ? "Posting…" : "Post GRN — Update Stock"}
          </Btn>
        )}
        <Btn variant="secondary" onClick={() => downloadGRNPDF(grn, "download")}>⬇ Download PDF</Btn>
        <Btn variant="secondary" onClick={() => downloadGRNPDF(grn, "print")}>🖨 Print</Btn>
      </div>
      {grn.posted_at && (
        <div
          style={{
            background: "#f0fdf4",
            border: `1px solid #bbf7d0`,
            borderRadius: 8,
            padding: "10px 16px",
            marginBottom: 16,
            fontFamily: MONO,
            fontSize: 12,
            color: GREEN,
          }}
        >
          ✓ Posted {new Date(grn.posted_at).toLocaleString("en-KE")} —
          stock has been updated
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3,1fr)",
          gap: 14,
          marginBottom: 20,
        }}
      >
        {[
          ["Supplier", grn.supplier_name],
          ["Received Date", grn.received_date],
          ["Linked PO", grn.po_number || "Direct receive"],
          ["Invoice No.", grn.supplier_invoice_number || "—"],
          ["Delivery Note", grn.supplier_delivery_note || "—"],
          ["Received By", grn.received_by],
        ].map(([k, v]) => (
          <Card key={k} style={{ padding: "12px 16px" }}>
            <div
              style={{
                fontSize: 10,
                color: MUTED,
                fontFamily: MONO,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                marginBottom: 4,
              }}
            >
              {k}
            </div>
            <div style={{ fontFamily: MONO, fontWeight: 600, fontSize: 13 }}>
              {v}
            </div>
          </Card>
        ))}
      </div>

      <Card style={{ padding: 0 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: SAND }}>
              {[
                "Product",
                "SKU",
                "Received",
                "Unit",
                "Base Rcvd",
                "Damaged",
                "Rejected",
                "Accepted",
                "Cost/Unit",
                "Line Total",
                "Batch",
                "Expiry",
              ].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: "10px 12px",
                    textAlign: "left",
                    fontSize: 10,
                    fontFamily: MONO,
                    color: MUTED,
                    fontWeight: 600,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    borderBottom: `1px solid ${BONE}`,
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grn.items.map((item, i) => (
              <tr
                key={item.id}
                style={{
                  borderBottom:
                    i < grn.items.length - 1 ? `1px solid ${BONE}` : "none",
                }}
              >
                <td
                  style={{
                    padding: "10px 12px",
                    fontFamily: MONO,
                    fontSize: 12,
                    fontWeight: 600,
                  }}
                >
                  {item.product_name}
                </td>
                <td
                  style={{
                    padding: "10px 12px",
                    fontFamily: MONO,
                    fontSize: 11,
                    color: MUTED,
                  }}
                >
                  {item.product_sku}
                </td>
                <td style={{ padding: "10px 12px", fontFamily: MONO, fontSize: 12 }}>
                  {item.received_qty_purchase} {item.purchase_unit_type}
                </td>
                <td
                  style={{
                    padding: "10px 12px",
                    fontFamily: MONO,
                    fontSize: 11,
                    color: MUTED,
                  }}
                >
                  ×{item.units_per_purchase}
                </td>
                <td
                  style={{
                    padding: "10px 12px",
                    fontFamily: MONO,
                    fontSize: 12,
                    fontWeight: 600,
                  }}
                >
                  {item.received_qty_base.toLocaleString()}
                </td>
                <td
                  style={{
                    padding: "10px 12px",
                    fontFamily: MONO,
                    fontSize: 12,
                    color: item.damaged_qty_base > 0 ? AMBER : MUTED,
                  }}
                >
                  {item.damaged_qty_base}
                </td>
                <td
                  style={{
                    padding: "10px 12px",
                    fontFamily: MONO,
                    fontSize: 12,
                    color: item.rejected_qty_base > 0 ? RED : MUTED,
                  }}
                >
                  {item.rejected_qty_base}
                </td>
                <td
                  style={{
                    padding: "10px 12px",
                    fontFamily: MONO,
                    fontSize: 13,
                    fontWeight: 700,
                    color: GREEN,
                  }}
                >
                  {item.accepted_qty_base.toLocaleString()}
                </td>
                <td style={{ padding: "10px 12px", fontFamily: MONO, fontSize: 12 }}>
                  {fmtKES(item.cost_per_base_unit)}
                </td>
                <td
                  style={{
                    padding: "10px 12px",
                    fontFamily: MONO,
                    fontSize: 12,
                    fontWeight: 600,
                  }}
                >
                  {fmtKES(item.line_total)}
                </td>
                <td
                  style={{
                    padding: "10px 12px",
                    fontFamily: MONO,
                    fontSize: 11,
                    color: MUTED,
                  }}
                >
                  {item.batch_number || "—"}
                </td>
                <td
                  style={{
                    padding: "10px 12px",
                    fontFamily: MONO,
                    fontSize: 11,
                    color: MUTED,
                  }}
                >
                  {item.expiry_date || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
