import { useMemo, useState, useRef, useEffect } from "react";

export default function CashSessionCloseModal({
  isOpen,
  session,
  onSubmit,
  onClose,
  loading,
  error,
}) {
  const [countedCash, setCountedCash] = useState("");
  const [notes, setNotes] = useState("");
  const [validationError, setValidationError] = useState("");
  const countedCashInputRef = useRef(null);

  const variance = useMemo(
  () => (parseFloat(countedCash) || 0) - (parseFloat(session?.expected_cash) || 0),
  [countedCash, session?.expected_cash]
);

  useEffect(() => {
    if (isOpen && countedCashInputRef.current) {
      countedCashInputRef.current.focus();
    }
  }, [isOpen]);

  const handleSubmit = () => {
    setValidationError("");

    if (!countedCash.trim()) {
      setValidationError("Counted cash is required");
      countedCashInputRef.current?.focus();
      return;
    }

    const countedValue = parseFloat(countedCash);
    if (isNaN(countedValue) || countedValue < 0) {
      setValidationError("Counted cash must be a valid number (zero or greater)");
      countedCashInputRef.current?.focus();
      return;
    }

    onSubmit?.({
      counted_cash: countedValue,
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
          Close Shift
        </h2>

        <p
          style={{
            margin: "0 0 20px 0",
            fontSize: "13px",
            color: "#666",
            lineHeight: "1.4",
          }}
        >
          Enter the total cash in the drawer after sales.
        </p>

        <div
          style={{
            marginBottom: "20px",
            padding: "12px",
            background: "#f3f4f6",
            borderRadius: "4px",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "12px",
          }}
        >
          <div>
            <div
              style={{
                fontSize: "11px",
                fontWeight: 600,
                color: "#6b7280",
                textTransform: "uppercase",
                marginBottom: "4px",
              }}
            >
              Opening Float
            </div>
            <div
              style={{
                fontSize: "16px",
                fontWeight: 700,
                color: "#111827",
              }}
            >
              {(session?.opening_float || 0).toFixed(2)} KES
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: "11px",
                fontWeight: 600,
                color: "#6b7280",
                textTransform: "uppercase",
                marginBottom: "4px",
              }}
            >
              Variance
            </div>
            <div
              style={{
                fontSize: "16px",
                fontWeight: 700,
                color: variance < 0 ? "#dc2626" : variance > 0 ? "#16a34a" : "#6b7280",
              }}
            >
              {variance >= 0 ? "+" : ""}{variance.toFixed(2)} KES
            </div>
          </div>
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
            Counted Cash (KES)
          </label>
          <input
            ref={countedCashInputRef}
            type="number"
            value={countedCash}
            onChange={(e) => setCountedCash(e.target.value)}
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
            placeholder="e.g., Counted twice, confirmed"
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
              opacity: loading ? 0.5 : 1,
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
            {loading ? "Closing..." : "Close Shift"}
          </button>
        </div>
      </div>
    </div>
  );
}