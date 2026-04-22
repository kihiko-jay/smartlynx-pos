import { useState, useEffect } from "react";

export function usePOSReceipts() {
  const [receipt, setReceipt] = useState(null);
  const [lastReceipt, setLastReceipt] = useState(null);

  // Load last receipt from localStorage on mount
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("dukapos_last_receipt") || "null");
      setLastReceipt(saved || null);
    } catch {
      setLastReceipt(null);
    }
  }, []);

  const saveLastReceipt = (receiptData) => {
    setLastReceipt(receiptData);
    localStorage.setItem("dukapos_last_receipt", JSON.stringify(receiptData));
  };

  const clearReceipt = () => {
    setReceipt(null);
  };

  return {
    receipt,
    setReceipt,
    lastReceipt,
    setLastReceipt,
    saveLastReceipt,
    clearReceipt,
  };
}
