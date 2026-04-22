import { useState, useEffect } from "react";
import { productsAPI } from "../../api/client";

export function usePOSEntry() {
  const [entryInput, setEntryInput] = useState("");
  const [entryLoading, setEntryLoading] = useState(false);

  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchIdx, setSearchIdx] = useState(0);

  const [error, setError] = useState("");

  // Debounced product search
  useEffect(() => {
    if (!showSearch || !searchQuery.trim()) {
      setSearchResults([]);
      setSearchIdx(0);
      return;
    }
    const t = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const res = await productsAPI.list({
          is_active: true,
          search: searchQuery.trim(),
          limit: 12,
        });
        // Normalize API response to always be an array
        const results = Array.isArray(res)
          ? res
          : res?.items || res?.data || res?.products || [];
        setSearchResults(results);
        setSearchIdx(0);
      } catch (e) {
        setError(e.message);
      } finally {
        setSearchLoading(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [searchQuery, showSearch]);

  const appendEntryDigit = (value) => {
    if (showSearch) {
      setSearchQuery((prev) => `${prev}${value}`);
    } else {
      setEntryInput((prev) => `${prev}${value}`);
    }
  };

  const backspaceEntry = () => {
    if (showSearch) {
      setSearchQuery((prev) => prev.slice(0, -1));
    } else {
      setEntryInput((prev) => prev.slice(0, -1));
    }
  };

  const openSearch = (prefill = "") => {
    setSearchQuery(prefill);
    setSearchResults([]);
    setSearchIdx(0);
    setShowSearch(true);
  };

  const closeSearch = () => {
    setShowSearch(false);
    setSearchQuery("");
    setSearchResults([]);
  };

  return {
    entryInput,
    setEntryInput,
    entryLoading,
    setEntryLoading,
    showSearch,
    setShowSearch,
    searchQuery,
    setSearchQuery,
    searchResults,
    setSearchResults,
    searchLoading,
    searchIdx,
    setSearchIdx,
    error,
    setError,
    appendEntryDigit,
    backspaceEntry,
    openSearch,
    closeSearch,
  };
}
