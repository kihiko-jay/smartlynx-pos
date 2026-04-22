import { useState, useMemo } from "react";

export function usePOSCart() {
  const [cart, setCart] = useState([]);
  const [selectedCartId, setSelectedCartId] = useState(null);
  const [editingQtyId, setEditingQtyId] = useState(null);

  const selectedItem = useMemo(
    () => cart.find((item) => item.id === selectedCartId) || null,
    [cart, selectedCartId]
  );

  const addProductToCart = (product) => {
    setCart((prev) => {
      const existing = prev.find((i) => i.id === product.id);
      if (existing) {
        const updated = prev.map((i) =>
          i.id === product.id ? { ...i, qty: i.qty + 1 } : i
        );
        setSelectedCartId(product.id);
        return updated;
      }
      setSelectedCartId(product.id);
      return [...prev, { ...product, qty: 1 }];
    });
    setEditingQtyId(null);
  };

  const handleQtyChange = (id, newQty) => {
    let qty = parseInt(newQty, 10);
    if (isNaN(qty) || qty < 1) qty = 1;
    setCart((prev) => prev.map((i) => (i.id === id ? { ...i, qty } : i)));
  };

  const adjustSelectedQty = (delta) => {
    if (!selectedItem) return;
    const nextQty = Math.max(1, selectedItem.qty + delta);
    handleQtyChange(selectedItem.id, nextQty);
  };

  const removeItem = (id) => {
    const remaining = cart.filter((i) => i.id !== id);
    setCart(remaining);
    setEditingQtyId(null);
    if (selectedCartId === id) {
      setSelectedCartId(remaining[0]?.id || null);
    }
  };

  const clearCart = () => {
    setCart([]);
    setSelectedCartId(null);
    setEditingQtyId(null);
  };

  return {
    cart,
    setCart,
    selectedCartId,
    setSelectedCartId,
    editingQtyId,
    setEditingQtyId,
    selectedItem,
    addProductToCart,
    handleQtyChange,
    adjustSelectedQty,
    removeItem,
    clearCart,
  };
}
