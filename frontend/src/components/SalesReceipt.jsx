// src/components/SaleReceipt.jsx
import React from "react";
import { fmtKES, getSession } from "../api/client";

function formatDateTime(value) {
  if (!value) return new Date().toLocaleString("en-KE");
  try {
    return new Date(value).toLocaleString("en-KE", {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(value);
  }
}

function roundToNearestHundredth(value) {
  return Math.round(value);
}

function fmtKESNoDecimals(value) {
  const num = Number(value ?? 0);
  if (isNaN(num)) return "KES 0";
  const wholeNumber = Math.round(num);
  return `KES ${wholeNumber.toLocaleString("en-KE")}`;
}

export default function SaleReceipt({
  receipt,
  storeName = "Smartlynx Demo Store",
  storeLocation = "Nairobi, Kenya",
  showActions = false,
  onPrint,
  onWhatsApp,
  onNewSale,
}) {
  const session = getSession();

  if (!receipt) return null;

  const items = receipt.items || [];
  const subtotal =
    receipt.subtotal != null
      ? Number(receipt.subtotal)
      : items.reduce((sum, item) => {
          const qty = Number(item.qty || 0);
          const unitPrice = Number(item.unit_price || item.selling_price || item.price || 0);
          const discount = Number(item.discount || 0);
          return sum + qty * unitPrice - discount;
        }, 0);

  const vatAmount = Number(receipt.vat_amount || 0);
  const total = Number(receipt.total || 0);
  const cashTendered =
    receipt.cash_tendered != null ? Number(receipt.cash_tendered) : null;
  const changeGiven =
    receipt.change_given != null ? Number(receipt.change_given) : null;

  return (
    <div
      style={{
        background: "#ffffff",
        color: "#111827",
        borderRadius: 12,
        border: "1px solid #e5e7eb",
        padding: 20,
        maxWidth: 420,
        width: "100%",
        margin: "0 auto",
        boxShadow: "0 10px 30px rgba(0,0,0,0.08)",
        fontFamily: "'Inter', Arial, sans-serif",
      }}
    >
      <div style={{ textAlign: "center", marginBottom: 16 }}>
        <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: 0.3 }}>
          {storeName}
        </div>
        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
          {storeLocation}
        </div>
        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
          Thank you for shopping with us
        </div>
      </div>

      <div
        style={{
          borderTop: "1px dashed #d1d5db",
          borderBottom: "1px dashed #d1d5db",
          padding: "10px 0",
          marginBottom: 14,
          fontSize: 12,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span>Receipt No</span>
          <strong>{receipt.txn_number || "—"}</strong>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span>Date</span>
          <span>{formatDateTime(receipt.completed_at || receipt.created_at)}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span>Cashier</span>
          <span>{session?.name || "Cashier"}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Payment</span>
          <span style={{ textTransform: "uppercase" }}>
            {receipt.payment_method || "cash"}
          </span>
        </div>
      </div>

      <div style={{ marginBottom: 14 }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 50px 50px 70px",
            gap: 6,
            fontSize: 11,
            fontWeight: 700,
            color: "#4b5563",
            marginBottom: 8,
          }}
        >
          <div>Item</div>
          <div style={{ textAlign: "right" }}>Price</div>
          <div style={{ textAlign: "center" }}>Qty</div>
          <div style={{ textAlign: "right" }}>Total</div>
        </div>

        {items.map((item, idx) => {
          const qty = Number(item.qty || 0);
          const unitPrice = Number(item.selling_price || item.unit_price || item.price || 0);
          const lineTotal = Number(item.line_total || 0);
          const itemVat = Number(item.vat_amount || 0);
          // Actual amount paid = line_total + vat_amount (includes VAT)
          const actualAmount = lineTotal + itemVat;

          return (
            <div
              key={item.id || idx}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 50px 50px 70px",
                gap: 6,
                fontSize: 12,
                padding: "8px 0",
                borderBottom: "1px solid #f3f4f6",
              }}
            >
              <div>
                <div style={{ fontWeight: 600 }}>
                  {item.product_name || item.name || "Item"}
                </div>
                <div style={{ color: "#6b7280", fontSize: 11 }}>
                  {item.sku || item.itemcode || ""}
                </div>
              </div>
              <div style={{ textAlign: "right", fontSize: 11 }}>
                {fmtKES(roundToNearestHundredth(unitPrice))}
              </div>
              <div style={{ textAlign: "center" }}>{qty}</div>
              <div style={{ textAlign: "right", fontWeight: 600 }}>
                {fmtKES(roundToNearestHundredth(actualAmount))}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ borderTop: "1px solid #e5e7eb", paddingTop: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 6 }}>
          <span>Subtotal</span>
          <span>{fmtKES(subtotal)}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 6 }}>
          <span>VAT</span>
          <span>{fmtKES(vatAmount)}</span>
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 16,
            fontWeight: 800,
            marginTop: 10,
            marginBottom: 8,
          }}
        >
          <span>TOTAL</span>
          <span>{fmtKESNoDecimals(total)}</span>
        </div>

        {cashTendered !== null && (
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
            <span>Cash</span>
            <span>{fmtKESNoDecimals(cashTendered)}</span>
          </div>
        )}

        {changeGiven !== null && (
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
            <span>Change</span>
            <span>{fmtKESNoDecimals(changeGiven)}</span>
          </div>
        )}
      </div>

      <div style={{ marginTop: 16, textAlign: "center", fontSize: 11, color: "#6b7280" }}>
        {receipt.etims_synced ? "KRA eTIMS synced" : "eTIMS pending"}
      </div>

      {showActions && (
        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button
            onClick={onPrint}
            style={{
              flex: 1,
              padding: "10px 12px",
              borderRadius: 8,
              border: "1px solid #d1d5db",
              background: "#111827",
              color: "#fff",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Print
          </button>
          <button
            onClick={onWhatsApp}
            style={{
              flex: 1,
              padding: "10px 12px",
              borderRadius: 8,
              border: "1px solid #d1d5db",
              background: "#16a34a",
              color: "#fff",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            WhatsApp
          </button>
          <button
            onClick={onNewSale}
            style={{
              flex: 1,
              padding: "10px 12px",
              borderRadius: 8,
              border: "1px solid #d1d5db",
              background: "#f3f4f6",
              color: "#111827",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            New Sale
          </button>
        </div>
      )}
    </div>
  );
}