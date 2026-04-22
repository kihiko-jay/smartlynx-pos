import React, { useState, useEffect } from "react";

const getButtonStyle = (isMobile) => ({
  action: {
    background: "linear-gradient(180deg, #1b6cff 0%, #0d4fd6 100%)",
    border: "1px solid #2f65d9",
    borderRadius: 6,
    color: "#fff",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: isMobile ? 11 : 12,
    fontWeight: 700,
    letterSpacing: "0.04em",
    minHeight: isMobile ? 40 : 46,
    padding: isMobile ? "8px 10px" : "10px 12px",
    textTransform: "uppercase",
  },
  utility: {
    background: "#0f1724",
    border: "1px solid #22304a",
    borderRadius: 6,
    color: "#d6e2ff",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: isMobile ? 11 : 12,
    fontWeight: 700,
    minHeight: isMobile ? 40 : 46,
    padding: isMobile ? "8px 10px" : "8px 14px",
  },
});

export default function EntryLookup({
  entryInput,
  setEntryInput,
  entryLoading,
  handleEntryKeyDown,
  openSearch,
  clearEntry,
  entryRef,
}) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const buttonStyles = getButtonStyle(isMobile);
  const gridLayout = isMobile ? "1fr auto" : "1fr auto auto";

  return (
    <div className="rms-panel">
      <div className="rms-title">Entry / Lookup</div>
      <div style={{ padding: isMobile ? 8 : 12, display: "grid", gridTemplateColumns: gridLayout, gap: isMobile ? 4 : 8, alignItems: "center" }}>
        <input
          ref={entryRef}
          className="rms-input"
          placeholder={entryLoading ? "Looking up..." : (isMobile ? "Item code" : "Item code / barcode / SKU   ·   ENTER = add   ·   F2 = search")}
          value={entryInput}
          onChange={(e) => {
            setEntryInput(e.target.value);
          }}
          onKeyDown={handleEntryKeyDown}
          disabled={entryLoading}
          style={{ fontSize: isMobile ? 13 : 14, padding: isMobile ? "8px 10px" : "10px 12px" }}
        />
        <button style={buttonStyles.action} onClick={() => openSearch(entryInput)}>
          {isMobile ? "Find" : "Lookup"}
        </button>
        {!isMobile && (
          <button style={buttonStyles.utility} onClick={clearEntry}>
            Clear
          </button>
        )}
      </div>
    </div>
  );
}