import { useState, useRef, useEffect } from "react";

export default function CashSessionOpenModal({
  isOpen,
  onSubmit,
  onClose,
  loading,
  error,
  defaultTerminalId,
  isMandatory,
}) {
  const [openingFloat, setOpeningFloat] = useState("");
  const [terminalId, setTerminalId] = useState(defaultTerminalId || "");
  const [notes, setNotes] = useState("");
  const [validationError, setValidationError] = useState("");
  const floatInputRef = useRef(null);

  useEffect(() => {
    if (isOpen && floatInputRef.current) {
      floatInputRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    if (defaultTerminalId && !terminalId) {
      setTerminalId(defaultTerminalId);
    }
  }, [defaultTerminalId, terminalId]);

  const handleSubmit = () => {
    setValidationError("");

    if (!openingFloat.trim()) {
      setValidationError("Opening cash is required");
      floatInputRef.current?.focus();
      return;
    }

    const floatValue = parseFloat(openingFloat);
    if (isNaN(floatValue) || floatValue < 0) {
      setValidationError("Opening cash must be a valid number (zero or greater)");
      floatInputRef.current?.focus();
      return;
    }

    if (!terminalId.trim()) {
      setValidationError("Terminal ID is required");
      return;
    }

    onSubmit?.({
      opening_float: floatValue,
      terminal_id: terminalId.trim(),
      notes: notes.trim(),
    });
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: "8px",
          boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
          width: "90%",
          maxWidth: "400px",
          padding: "24px",
          fontFamily: "Tahoma, Verdana, Arial, sans-serif",
        }}
      >
        <h2
          style={{
            margin: "0 0 16px 0",
            fontSize: "18px",
            fontWeight: 700,
            color: "#111827",
          }}
        >
          Start Shift
        </h2>

        <p
          style={{
            margin: "0 0 20px 0",
            fontSize: "13px",
            color: "#666",
            lineHeight: "1.4",
          }}
        >
          Enter the amount of cash in the drawer before sales begin.
        </p>

        <div style={{ marginBottom: "16px" }}>
          <label
            style={{
              display: "block",
              fontSize: "12px",
              fontWeight: 600,
              color: "#155eef",
              marginBottom: "4px",
              textTransform: "uppercase",
            }}
          >
            Opening Cash (KES)
          </label>
          <input
            ref={floatInputRef}
            type="number"
            value={openingFloat}
            onChange={(e) => setOpeningFloat(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="0.00"
            disabled={loading}
            style={{
              width: "100%",
              padding: "10px 12px",
              border: "1px solid #cbd5e1",
              borderRadius: "4px",
              fontSize: "15px",
              fontFamily: "inherit",
              boxSizing: "border-box",
              outline: "none",
            }}
            onFocus={(e) =>
              (e.target.style.borderColor = "#155eef")
            }
            onBlur={(e) =>
              (e.target.style.borderColor = "#cbd5e1")
            }
          />
        </div>

        <div style={{ marginBottom: "16px" }}>
          <label
            style={{
              display: "block",
              fontSize: "12px",
              fontWeight: 600,
              color: "#155eef",
              marginBottom: "4px",
              textTransform: "uppercase",
            }}
          >
            Terminal ID
          </label>
          <input
            type="text"
            value={terminalId}
            onChange={(e) => setTerminalId(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g., T01"
            disabled={loading}
            style={{
              width: "100%",
              padding: "10px 12px",
              border: "1px solid #cbd5e1",
              borderRadius: "4px",
              fontSize: "15px",
              fontFamily: "inherit",
              boxSizing: "border-box",
              outline: "none",
            }}
            onFocus={(e) =>
              (e.target.style.borderColor = "#155eef")
            }
            onBlur={(e) =>
              (e.target.style.borderColor = "#cbd5e1")
            }
          />
        </div>

        <div style={{ marginBottom: "20px" }}>
          <label
            style={{
              display: "block",
              fontSize: "12px",
              fontWeight: 600,
              color: "#155eef",
              marginBottom: "4px",
              textTransform: "uppercase",
            }}
          >
            Notes (optional)
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g., Starting balance noted"
            disabled={loading}
            style={{
              width: "100%",
              padding: "10px 12px",
              border: "1px solid #cbd5e1",
              borderRadius: "4px",
              fontSize: "13px",
              fontFamily: "inherit",
              boxSizing: "border-box",
              outline: "none",
              minHeight: "60px",
              resize: "none",
            }}
            onFocus={(e) =>
              (e.target.style.borderColor = "#155eef")
            }
            onBlur={(e) =>
              (e.target.style.borderColor = "#cbd5e1")
            }
          />
        </div>

        {(validationError || error) && (
          <div
            style={{
              marginBottom: "16px",
              padding: "10px 12px",
              background: "#fee2e2",
              border: "1px solid #fca5a5",
              borderRadius: "4px",
              color: "#991b1b",
              fontSize: "13px",
            }}
          >
            {validationError || error}
          </div>
        )}

        <div
          style={{
            display: "flex",
            gap: "12px",
            justifyContent: "flex-end",
          }}
        >
          <button
             onClick={onClose}
  disabled={loading}
  style={{
    padding: "10px 20px",
    borderRadius: "4px",
    border: "1px solid #cbd5e1",
    background: "#f3f4f6",
    color: "#111827",
    fontWeight: 600,
    cursor: loading ? "not-allowed" : "pointer",
    fontSize: "14px",
    opacity: loading ? 0.6 : 1,
  }}
>
  Cancel
</button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{
              padding: "10px 20px",
              borderRadius: "4px",
              border: "none",
              background: loading ? "#cbd5e1" : "#155eef",
              color: "#fff",
              fontWeight: 600,
              cursor: loading ? "wait" : "pointer",
              fontSize: "14px",
            }}
          >
            {loading ? "Opening..." : "Start Shift"}
          </button>
        </div>
      </div>
    </div>
  );
}