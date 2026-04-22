import { useState, useEffect, useCallback } from "react";
import { procurementAPI, productsAPI } from "../../api/client";
import { MONO, SYNE, SAND, BONE, MUTED, GREEN, RED, fmtKES } from "./styles";
import { Card, Btn, Badge, Err, Loading, Input, Select, SectionHead } from "./UIComponents";

export default function InvoiceMatching() {
  const [matches, setMatches] = useState([]);
  const [loading, setL] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    supplier_id: "",
    purchase_order_id: "",
    grn_id: "",
    invoice_number: "",
    invoice_date: "",
    invoice_total: "",
  });
  const [suppliers, setSuppliers] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    setL(true);
    procurementAPI
      .listMatches({})
      .then(setMatches)
      .catch(console.error)
      .finally(() => setL(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    productsAPI
      .suppliers()
      .then((r) => {
        const list = Array.isArray(r) ? r : (r?.suppliers || r?.data || []);
        setSuppliers(Array.isArray(list) ? list : []);
      })
      .catch((e) => {
        console.error("Failed to load suppliers:", e);
        setSuppliers([]);
      });
  }, []);

  const submit = async () => {
    if (!form.supplier_id || !form.invoice_number || !form.invoice_total) {
      setErr("Supplier, invoice number, and total are required");
      return;
    }
    setSaving(true);
    setErr("");
    try {
      await procurementAPI.createMatch({
        ...form,
        supplier_id: parseInt(form.supplier_id),
        purchase_order_id: form.purchase_order_id
          ? parseInt(form.purchase_order_id)
          : null,
        grn_id: form.grn_id ? parseInt(form.grn_id) : null,
        invoice_total: parseFloat(form.invoice_total),
      });
      setShowForm(false);
      setForm({
        supplier_id: "",
        purchase_order_id: "",
        grn_id: "",
        invoice_number: "",
        invoice_date: "",
        invoice_total: "",
      });
      load();
    } catch (e) {
      setErr(e?.detail || e?.message || "Failed");
    } finally {
      setSaving(false);
    }
  };

  const resolve = async (id, status) => {
    try {
      await procurementAPI.resolveMatch(id, { matched_status: status });
      load();
    } catch (e) {
      alert(e?.detail || "Resolve failed");
    }
  };

  if (loading) return <Loading />;

  return (
    <div>
      <SectionHead
        title="Invoice Matching"
        sub="Match supplier invoices to POs and GRNs"
        action={
          <Btn onClick={() => setShowForm((s) => !s)}>
            {showForm ? "Cancel" : "+ Match Invoice"}
          </Btn>
        }
      />

      {showForm && (
        <Card style={{ marginBottom: 20 }}>
          <div
            style={{
              fontWeight: 700,
              fontFamily: MONO,
              fontSize: 13,
              marginBottom: 16,
            }}
          >
            New Invoice Match
          </div>
          <Err msg={err} />
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr 1fr",
              gap: 12,
              marginBottom: 16,
            }}
          >
            <Select
              label="Supplier *"
              value={form.supplier_id}
              onChange={(e) =>
                setForm((f) => ({ ...f, supplier_id: e.target.value }))
              }
            >
              <option value="">— select —</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
            <Input
              label="Invoice Number *"
              value={form.invoice_number}
              onChange={(e) =>
                setForm((f) => ({ ...f, invoice_number: e.target.value }))
              }
            />
            <Input
              label="Invoice Date"
              type="date"
              value={form.invoice_date}
              onChange={(e) =>
                setForm((f) => ({ ...f, invoice_date: e.target.value }))
              }
            />
            <Input
              label="Invoice Total (KES) *"
              type="number"
              value={form.invoice_total}
              onChange={(e) =>
                setForm((f) => ({ ...f, invoice_total: e.target.value }))
              }
            />
            <Input
              label="PO ID (optional)"
              type="number"
              value={form.purchase_order_id}
              onChange={(e) =>
                setForm((f) => ({ ...f, purchase_order_id: e.target.value }))
              }
            />
            <Input
              label="GRN ID (optional)"
              type="number"
              value={form.grn_id}
              onChange={(e) =>
                setForm((f) => ({ ...f, grn_id: e.target.value }))
              }
            />
          </div>
          <Btn onClick={submit} disabled={saving}>
            {saving ? "Matching…" : "Create Match"}
          </Btn>
        </Card>
      )}

      {matches.length === 0 ? (
        <Card>
          <div
            style={{
              textAlign: "center",
              color: MUTED,
              padding: 40,
              fontFamily: MONO,
            }}
          >
            No invoice matches yet.
          </div>
        </Card>
      ) : (
        <Card style={{ padding: 0 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: SAND }}>
                {[
                  "Invoice No.",
                  "Supplier",
                  "PO",
                  "GRN",
                  "Invoice Total",
                  "Status",
                  "Variance",
                  "Actions",
                ].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: "10px 14px",
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
              {matches.map((m, i) => {
                let variance = null;
                try {
                  variance = m.variance_json
                    ? JSON.parse(m.variance_json)
                    : null;
                } catch {}
                const hasDisc = variance?.has_discrepancy;
                return (
                  <tr
                    key={m.id}
                    style={{
                      borderBottom:
                        i < matches.length - 1 ? `1px solid ${BONE}` : "none",
                    }}
                  >
                    <td
                      style={{
                        padding: "10px 14px",
                        fontFamily: MONO,
                        fontSize: 12,
                        fontWeight: 600,
                      }}
                    >
                      {m.invoice_number}
                    </td>
                    <td
                      style={{
                        padding: "10px 14px",
                        fontFamily: MONO,
                        fontSize: 12,
                      }}
                    >
                      {m.supplier_name}
                    </td>
                    <td
                      style={{
                        padding: "10px 14px",
                        fontFamily: MONO,
                        fontSize: 11,
                        color: MUTED,
                      }}
                    >
                      {m.po_number || "—"}
                    </td>
                    <td
                      style={{
                        padding: "10px 14px",
                        fontFamily: MONO,
                        fontSize: 11,
                        color: MUTED,
                      }}
                    >
                      {m.grn_number || "—"}
                    </td>
                    <td
                      style={{
                        padding: "10px 14px",
                        fontFamily: MONO,
                        fontSize: 12,
                        fontWeight: 600,
                      }}
                    >
                      {fmtKES(m.invoice_total)}
                    </td>
                    <td style={{ padding: "10px 14px" }}>
                      <Badge status={m.matched_status} />
                    </td>
                    <td
                      style={{
                        padding: "10px 14px",
                        fontFamily: MONO,
                        fontSize: 12,
                        color: hasDisc ? RED : GREEN,
                      }}
                    >
                      {variance
                        ? hasDisc
                          ? `⚠ ${fmtKES(Math.abs(variance.total_variance || 0))}`
                          : "✓ No variance"
                        : "—"}
                    </td>
                    <td style={{ padding: "10px 14px" }}>
                      {m.matched_status === "unmatched" && (
                        <div style={{ display: "flex", gap: 6 }}>
                          <Btn
                            onClick={() => resolve(m.id, "matched")}
                            style={{
                              fontSize: 11,
                              padding: "4px 8px",
                              cursor: "pointer",
                            }}
                            variant="success"
                          >
                            Match
                          </Btn>
                          <Btn
                            onClick={() => resolve(m.id, "disputed")}
                            style={{
                              fontSize: 11,
                              padding: "4px 8px",
                              cursor: "pointer",
                            }}
                            variant="danger"
                          >
                            Dispute
                          </Btn>
                        </div>
                      )}
                      {m.matched_status === "matched" && (
                        <Badge status="matched" />
                      )}
                      {m.matched_status === "disputed" && (
                        <Badge status="disputed" />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
