import { productsAPI } from "../api/client";

export const productService = {
  // Lookup product by entry (barcode, SKU, or item code)
  lookupProduct: async (searchValue) => {
    if (!searchValue) return null;

    let product = null;

    // Try as item code (numeric)
    if (/^\d+$/.test(searchValue)) {
      try {
        product = await productsAPI.getByItemCode(searchValue);
        if (product) return product;
      } catch {}
    }

    // Try as barcode
    try {
      product = await productsAPI.getByBarcode(searchValue);
      if (product) return product;
    } catch {}

    // Try as SKU
    try {
      const list = await productsAPI.list({
        is_active: true,
        sku: searchValue,
        limit: 1,
      });
      if (list?.length) return list[0];
    } catch {}

    return null;
  },

  // Search products by query
  searchProducts: async (query, limit = 12) => {
    try {
      const res = await productsAPI.list({
        is_active: true,
        search: query.trim(),
        limit,
      });
      return res || [];
    } catch (e) {
      throw new Error(e.message || "Product search failed");
    }
  },
};
