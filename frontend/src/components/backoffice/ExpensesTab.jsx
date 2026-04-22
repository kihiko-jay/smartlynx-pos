/**
 * ExpensesTab — Expense Vouchers module for BackOffice.
 *
 * Orchestrates two views:
 *   list — filterable expense voucher table (default)
 *   form — create new voucher
 *
 * After a save the tab returns to list and increments refreshKey
 * so the list re-fetches without a full page reload.
 */

import { useState } from "react";
import ExpenseVoucherList from "../expenses/ExpenseVoucherList";
import ExpenseVoucherForm from "../expenses/ExpenseVoucherForm";

export default function ExpensesTab() {
  const [view, setView] = useState("list"); // "list" | "form"
  const [refreshKey, setRefreshKey] = useState(0);

  const handleSaved = () => {
    setView("list");
    setRefreshKey((k) => k + 1);
  };

  if (view === "form") {
    return (
      <ExpenseVoucherForm
        onSaved={handleSaved}
        onBack={() => setView("list")}
      />
    );
  }

  return (
    <ExpenseVoucherList
      onCreateNew={() => setView("form")}
      refreshKey={refreshKey}
    />
  );
}
