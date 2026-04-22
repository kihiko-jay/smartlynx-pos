import { useState, useEffect } from "react";

export function usePOSHolds() {
  const [heldSales, setHeldSales] = useState([]);
  const [showHoldList, setShowHoldList] = useState(false);

  // Load held sales from localStorage on mount
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("dukapos_held_sales") || "[]");
      setHeldSales(Array.isArray(saved) ? saved : []);
    } catch {
      setHeldSales([]);
    }
  }, []);

  const saveHeldSales = (holds) => {
    setHeldSales(holds);
    localStorage.setItem("dukapos_held_sales", JSON.stringify(holds));
  };

  return {
    heldSales,
    setHeldSales,
    showHoldList,
    setShowHoldList,
    saveHeldSales,
  };
}
