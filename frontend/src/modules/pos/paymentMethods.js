export const PAYMENT_METHODS = [
  { id: "cash", label: "Cash", requiresAmount: true },
  { id: "mpesa", label: "M-Pesa", requiresAmount: false },
  { id: "card", label: "Card", requiresAmount: false },
  { id: "credit", label: "Credit", requiresAmount: false },
  { id: "store_credit", label: "Store Credit", requiresAmount: false },
];

export const DEFAULT_PAYMENT_METHOD = PAYMENT_METHODS[0].id;
