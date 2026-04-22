import React from "react";

function KeypadButton({ children, onClick, accent = false, success = false, danger = false, isMobile = false }) {
  let bg = "#1570ef";
  let border = "#2f65d9";
  let color = "#fff";

  if (accent) {
    bg = "#0f1724";
    border = "#22304a";
    color = "#d6e2ff";
  }
  if (success) {
    bg = "#0f8f36";
    border = "#22a04b";
  }
  if (danger) {
    bg = "#b42318";
    border = "#d92d20";
  }

  return (
    <button
      onClick={onClick}
      style={{
        background: bg,
        border: `1px solid ${border}`,
        borderRadius: 6,
        color,
        cursor: "pointer",
        fontFamily: "inherit",
        fontSize: isMobile ? 14 : 18,
        fontWeight: 800,
        minHeight: isMobile ? 44 : 58,
        padding: isMobile ? "8px 4px" : "10px 6px",
      }}
    >
      {children}
    </button>
  );
}

export default function NumericKeypad({
  appendEntryDigit,
  backspaceEntry,
  showSearch,
  closeSearch,
  clearEntry,
  handleEntryKeyDown,
  searchResults,
  searchIdx,
  addProductToCart,
  closeSearch: closeSearchProp,
}) {
  const [isMobile, setIsMobile] = React.useState(typeof window !== "undefined" && window.innerWidth < 768);

  React.useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div className="rms-panel" style={{ padding: isMobile ? 6 : 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: isMobile ? 4 : 8, alignContent: "start" }}>
        <KeypadButton isMobile={isMobile} onClick={() => appendEntryDigit("7")}>7</KeypadButton>
        <KeypadButton isMobile={isMobile} onClick={() => appendEntryDigit("8")}>8</KeypadButton>
        <KeypadButton isMobile={isMobile} onClick={() => appendEntryDigit("9")}>9</KeypadButton>
        <KeypadButton isMobile={isMobile} onClick={() => appendEntryDigit("4")}>4</KeypadButton>
        <KeypadButton isMobile={isMobile} onClick={() => appendEntryDigit("5")}>5</KeypadButton>
        <KeypadButton isMobile={isMobile} onClick={() => appendEntryDigit("6")}>6</KeypadButton>
        <KeypadButton isMobile={isMobile} onClick={() => appendEntryDigit("1")}>1</KeypadButton>
        <KeypadButton isMobile={isMobile} onClick={() => appendEntryDigit("2")}>2</KeypadButton>
        <KeypadButton isMobile={isMobile} onClick={() => appendEntryDigit("3")}>3</KeypadButton>
        <KeypadButton isMobile={isMobile} accent onClick={backspaceEntry}>⌫</KeypadButton>
        <KeypadButton isMobile={isMobile} onClick={() => appendEntryDigit("0")}>0</KeypadButton>
        <KeypadButton isMobile={isMobile} danger onClick={() => (showSearch ? closeSearch() : clearEntry())}>CLR</KeypadButton>
        <div style={{ gridColumn: "1 / -1", display: "grid", gridTemplateColumns: "1fr 1fr", gap: isMobile ? 4 : 8 }}>
          <KeypadButton isMobile={isMobile} accent onClick={() => appendEntryDigit(".")}>.</KeypadButton>
          <KeypadButton
            isMobile={isMobile}
            success
            onClick={() => {
              if (showSearch && searchResults[searchIdx]) {
                addProductToCart(searchResults[searchIdx]);
                closeSearchProp();
                return;
              }
              const fakeEvent = { key: "Enter", preventDefault() {} };
              handleEntryKeyDown(fakeEvent);
            }}
          >
            OK
          </KeypadButton>
        </div>
      </div>
    </div>
  );
}