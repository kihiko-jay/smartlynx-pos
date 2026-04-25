import { parseMoneyToCents, mulCentsByQty, subCents, fmtKESCents } from "../../utils/money";

function lineTotalCentsFromItem(item) {
  if (item.line_total != null && item.line_total !== "") {
    return parseMoneyToCents(item.line_total);
  }
  const unit = parseMoneyToCents(item.unit_price || item.selling_price || item.price || 0);
  const qty = Number(item.qty || 0);
  const disc = parseMoneyToCents(item.discount || 0);
  return subCents(mulCentsByQty(unit, qty), disc);
}

export const receiptFlow = {
  buildReceiptText: (receipt, storeName = "Smartlynx Store") => {
    const lines = [];
    lines.push("DUKAPOS RECEIPT");
    lines.push(`Receipt: ${receipt.txn_number || "-"}`);
    lines.push(
      `Date: ${new Date(
        receipt.completed_at || receipt.created_at || Date.now()
      ).toLocaleString("en-KE")}`
    );
    lines.push("");

    (receipt.items || []).forEach((item) => {
      const name = item.product_name || item.name || "Item";
      const qty = item.qty || 0;
      const lt = lineTotalCentsFromItem(item);
      lines.push(`${name} x${qty} - ${fmtKESCents(lt)}`);
    });

    lines.push("");
    lines.push(`Total: ${fmtKESCents(parseMoneyToCents(receipt.total || 0))}`);
    lines.push(`Payment: ${(receipt.payment_method || "cash").toUpperCase()}`);
    lines.push("");
    lines.push("Thank you for shopping with us");
    return lines.join("\n");
  },

  buildReceiptHtml: (receipt, storeName = "Smartlynx Store", storeLocation = "Kenya") => {
    const itemsHtml = (receipt.items || [])
      .map((item) => {
        const name = item.product_name || item.name || "Item";
        const qty = item.qty || 0;
        const lt = lineTotalCentsFromItem(item);
        return `
          <div class="item">
            <div>${name}</div>
            <div class="row"><span>${qty} x</span><span>${fmtKESCents(lt)}</span></div>
          </div>`;
      })
      .join("");

    return `
    <html>
      <head>
        <title>Receipt ${receipt.txn_number || ""}</title>
        <style>
          @page { size: 80mm auto; margin: 4mm; }
          body { font-family: 'Courier New', monospace; color: #000; padding: 0; margin: 0; }
          .wrap { width: 72mm; margin: 0 auto; padding: 4mm 0; }
          .center { text-align: center; }
          .line { border-top: 1px dashed #777; margin: 8px 0; }
          .row { display:flex; justify-content:space-between; font-size:12px; margin:2px 0; }
          .item { font-size:12px; margin:6px 0; }
          .total { font-size:16px; font-weight:700; }
        </style>
      </head>
      <body>
        <div class="wrap">
          <div class="center">
            <div style="font-weight:700;font-size:16px;">DUKAPOS</div>
            <div style="font-weight:700;font-size:14px;">${storeName || "Smartlynx Store"}</div>
            <div>${storeLocation || "Kenya"}</div>
          </div>
          <div class="line"></div>
          <div class="row"><span>Receipt</span><span>${receipt.txn_number || "-"}</span></div>
          <div class="row"><span>Date</span><span>${new Date(
            receipt.completed_at || receipt.created_at || Date.now()
          ).toLocaleString("en-KE")}</span></div>
          <div class="row"><span>Payment</span><span>${(
            receipt.payment_method || "cash"
          ).toUpperCase()}</span></div>
          <div class="line"></div>
          ${itemsHtml}
          <div class="line"></div>
          <div class="row"><span>Subtotal</span><span>${fmtKESCents(
            parseMoneyToCents(receipt.subtotal ?? receipt.gross_subtotal ?? 0)
          )}</span></div>
          <div class="row"><span>VAT</span><span>${fmtKESCents(parseMoneyToCents(receipt.vat_amount || 0))}</span></div>
          <div class="row total"><span>TOTAL</span><span>${fmtKESCents(parseMoneyToCents(receipt.total || 0))}</span></div>
          <div class="line"></div>
          <div class="center">Thank you. Please come again.</div>
        </div>
        <script>
          window.onload = () => { window.print(); setTimeout(() => window.close(), 300); };
        </script>
      </body>
    </html>`;
  },

  printReceipt: (receipt, storeName = "Smartlynx Store", storeLocation = "Kenya") => {
    if (!receipt) return;
    const printWindow = window.open("", "_blank", "width=360,height=700");
    if (!printWindow) return;
    printWindow.document.open();
    printWindow.document.write(receiptFlow.buildReceiptHtml(receipt, storeName, storeLocation));
    printWindow.document.close();
  },

  shareViaWhatsApp: (receipt, storeName = "Smartlynx Store") => {
    if (!receipt) return;
    const text = receiptFlow.buildReceiptText(receipt, storeName);
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
  },
};
