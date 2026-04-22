import { productService } from "../../services/productService";

export const entryActions = {
  // Handle entry submission (barcode/SKU lookup)
  handleEntrySubmit: async (entryValue, addProductToCart, onNotFound) => {
    if (!entryValue) return;

    try {
      const product = await productService.lookupProduct(entryValue);

      if (product) {
        addProductToCart(product);
        return { success: true, product };
      } else {
        onNotFound?.(entryValue);
        return { success: false, notFound: true };
      }
    } catch (err) {
      throw new Error(err.message || "Product lookup failed");
    }
  },

  // Handle search navigation
  handleSearchNavigation: (e, searchResults, searchIdx, setSearchIdx, addProductToCart, closeSearch) => {
    const results = Array.isArray(searchResults) ? searchResults : [];
    
    if (e.key === "Escape") {
      closeSearch?.();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSearchIdx?.((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSearchIdx?.((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results[searchIdx]) {
        addProductToCart?.(results[searchIdx]);
        closeSearch?.();
      }
    }
  },
};
