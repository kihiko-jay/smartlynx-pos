// Shell styles for Back Office UI
export const shellStyles = {
  app: {
    fontFamily: "Tahoma, Verdana, Arial, sans-serif",
    background: "#d7dee8",
    color: "#111827",
    minHeight: "100vh",
  },
  titleBar: (isMobile) => ({
    background: "linear-gradient(180deg, #0d58d2 0%, #04389c 100%)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: isMobile ? "10px 12px" : "12px 18px",
    borderBottom: "2px solid #022b76",
    position: "sticky",
    top: 0,
    zIndex: 20,
    flexWrap: isMobile ? "wrap" : "nowrap",
    gap: isMobile ? 8 : 12,
  }),
  panel: {
    background: "linear-gradient(180deg, #f6f8fb 0%, #edf2f8 100%)",
    border: "1px solid #9eb2ce",
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.75)",
    borderRadius: 10,
    overflow: "hidden",
  },
  panelTitle: (isMobile) => ({
    background: "linear-gradient(180deg, #155eef 0%, #003eb3 100%)",
    color: "#fff",
    fontWeight: 700,
    letterSpacing: ".03em",
    padding: isMobile ? "6px 10px" : "8px 12px",
    borderBottom: "1px solid #0b3186",
    textTransform: "uppercase",
    fontSize: isMobile ? 11 : 12,
  }),
  tabButton: (active, isMobile) => ({
    padding: isMobile ? "8px 10px" : "10px 14px",
    borderRadius: 8,
    border: `1px solid ${active ? "#2f65d9" : "#bfd0ea"}`,
    background: active
      ? "linear-gradient(180deg, #1b6cff 0%, #0d4fd6 100%)"
      : "#f7f9fc",
    color: active ? "#fff" : "#22304a",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: isMobile ? 10 : 12,
    fontWeight: 700,
    letterSpacing: ".04em",
    textTransform: "uppercase",
    whiteSpace: "nowrap",
    minHeight: isMobile ? 30 : 36,
  }),
  statCard: (accent, isMobile) => ({
    background: "#fff",
    border: "1px solid #cbd5e1",
    borderLeft: `5px solid ${accent}`,
    borderRadius: 10,
    padding: isMobile ? "12px 14px" : "16px 18px",
    minHeight: isMobile ? 90 : 110,
  }),
  searchInput: {
    width: "100%",
    border: "1px solid #92a8c9",
    background: "#fff",
    borderRadius: 6,
    padding: "10px 12px",
    fontSize: 14,
    outline: "none",
  },
  smallButton: (isMobile) => ({
    background: "#0f1724",
    border: "1px solid #22304a",
    borderRadius: 8,
    color: "#d6e2ff",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: isMobile ? 10 : 12,
    fontWeight: 700,
    minHeight: isMobile ? 32 : 38,
    padding: isMobile ? "0 8px" : "0 12px",
  }),
  primaryButton: (isMobile) => ({
    background: "linear-gradient(180deg, #1b6cff 0%, #0d4fd6 100%)",
    border: "1px solid #2f65d9",
    borderRadius: 8,
    color: "#fff",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: isMobile ? 10 : 12,
    fontWeight: 700,
    minHeight: isMobile ? 32 : 38,
    padding: isMobile ? "0 8px" : "0 12px",
  }),
};

export const getResponsiveGridColumns = (isMobile, desktopColumns) => {
  if (isMobile) {
    // Default to single column on mobile, or 2 columns if more than 3 items
    return desktopColumns > 3 ? "repeat(2, minmax(0,1fr))" : "1fr";
  }
  return `repeat(${desktopColumns}, minmax(0,1fr))`;
};
