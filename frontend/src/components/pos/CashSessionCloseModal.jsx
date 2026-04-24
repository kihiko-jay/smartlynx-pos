import { useMemo, useState, useRef, useEffect } from "react";

export default function CashSessionCloseModal({
  isOpen,
  session,
  onSubmit,
  onClose,
  loading,
  error,
}) {
  const [paymentCounts, setPaymentCounts] = useState({
    cash: "",
    mpesa: "",
    card: "",
    credit: "",
    store_credit: "",
  });
  const [notes, setNotes] = useState("");
  const [validationError, setValidationError] = useState("");
  const cashInputRef = useRef(null);

  const totalCounted = useMemo(() => {
    return Object.values(paymentCounts).reduce((sum, val) => sum + (parseFloat(val) || 0), 0);
  }, [paymentCounts]);

  const cashVariance = useMemo(
    () => (parseFloat(paymentCounts.cash) || 0) - (parseFloat(session?.expected_cash) || 0),
    [paymentCounts.cash, session?.expected_cash]
  );

  const totalVariance = useMemo(() => {
    // For now, only cash has an expected amount, others are informational
    return cashVariance;
  }, [cashVariance]);

  useEffect(() => {
    if (isOpen && cashInputRef.current) {
      cashInputRef.current.focus();
    }
  }, [isOpen]);

  const handleSubmit = () => {
    setValidationError("");

    // Validate that at least cash is entered (required)
    if (!paymentCounts.cash.trim()) {
      setValidationError("Cash count is required");
      cashInputRef.current?.focus();
      return;
    }

    const cashValue = parseFloat(paymentCounts.cash);
    if (isNaN(cashValue) || cashValue < 0) {
      setValidationError("Cash count must be a valid number (zero or greater)");
      cashInputRef.current?.focus();
      return;
    }

    // Validate other payment methods
    for (const [method, value] of Object.entries(paymentCounts)) {
      if (method !== 'cash' && value.trim()) {
        const numValue = parseFloat(value);
        if (isNaN(numValue) || numValue < 0) {
          setValidationError(`${method.charAt(0).toUpperCase() + method.slice(1)} count must be a valid number (zero or greater)`);
          return;
        }
      }
    }

    onSubmit?.({
      payment_counts: {
        cash: cashValue,
        mpesa: parseFloat(paymentCounts.mpesa) || 0,
        card: parseFloat(paymentCounts.card) || 0,
        credit: parseFloat(paymentCounts.credit) || 0,
        store_credit: parseFloat(paymentCounts.store_credit) || 0,
      },
      total_counted: totalCounted,
      notes: notes.trim(),
    });
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  const updatePaymentCount = (method, value) => {
    setPaymentCounts(prev => ({
      ...prev,
      [method]: value
    }));
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
          Enter the total amounts received for each payment method during this shift.
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
              Cash Variance
            </div>
            <div
              style={{
                fontSize: "16px",
                fontWeight: 700,
                color: cashVariance < 0 ? "#dc2626" : cashVariance > 0 ? "#16a34a" : "#6b7280",
              }}
            >
              {cashVariance >= 0 ? "+" : ""}{cashVariance.toFixed(2)} KES
            </div>
          </div>
        </div>

        <div style={{ marginBottom: "16px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <div>
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
                Cash (KES) *
              </label>
              <input
                ref={cashInputRef}
                type="number"
                value={paymentCounts.cash}
                onChange={(e) => updatePaymentCount("cash", e.target.value)}
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
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "#6b7280",
                  marginBottom: "4px",
                  textTransform: "uppercase",
                }}
              >
                M-Pesa (KES)
              </label>
              <input
                type="number"
                value={paymentCounts.mpesa}
                onChange={(e) => updatePaymentCount("mpesa", e.target.value)}
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
          </div>
        </div>

        <div style={{ marginBottom: "16px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "16px" }}>
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "#6b7280",
                  marginBottom: "4px",
                  textTransform: "uppercase",
                }}
              >
                Card (KES)
              </label>
              <input
                type="number"
                value={paymentCounts.card}
                onChange={(e) => updatePaymentCount("card", e.target.value)}
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
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "#6b7280",
                  marginBottom: "4px",
                  textTransform: "uppercase",
                }}
              >
                Credit (KES)
              </label>
              <input
                type="number"
                value={paymentCounts.credit}
                onChange={(e) => updatePaymentCount("credit", e.target.value)}
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
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "#6b7280",
                  marginBottom: "4px",
                  textTransform: "uppercase",
                }}
              >
                Store Credit (KES)
              </label>
              <input
                type="number"
                value={paymentCounts.store_credit}
                onChange={(e) => updatePaymentCount("store_credit", e.target.value)}
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
          </div>
        </div>

        <div
          style={{
            marginBottom: "16px",
            padding: "12px",
            background: "#f0f9ff",
            borderRadius: "4px",
            border: "1px solid #0ea5e9",
          }}
        >
          <div
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "#0ea5e9",
              textTransform: "uppercase",
              marginBottom: "4px",
            }}
          >
            Total Counted
          </div>
          <div
            style={{
              fontSize: "18px",
              fontWeight: 700,
              color: "#0ea5e9",
            }}
          >
            {totalCounted.toFixed(2)} KES
          </div>
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