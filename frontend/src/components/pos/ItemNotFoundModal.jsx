export default function ItemNotFoundModal({ show, itemCode, onClose, onSearch }) {
  if (!show) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(3,15,39,.58)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 200,
        padding: 16,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
    >
      <div
        className="rms-panel"
        style={{
          width: "min(400px, 90vw)",
          textAlign: "center",
        }}
      >
        <div className="rms-title" style={{ color: "#dc2626", marginBottom: 16 }}>
          ⚠ Item Not Found
        </div>
        
        <div
          style={{
            padding: "20px 16px",
            fontSize: 14,
            color: "#475569",
            marginBottom: 16,
          }}
        >
          <div style={{ marginBottom: 12 }}>
            No product found with code:
          </div>
          <div
            style={{
              background: "#f1f5f9",
              padding: "8px 12px",
              borderRadius: 4,
              fontFamily: "monospace",
              fontWeight: 700,
              color: "#1e293b",
              marginBottom: 16,
            }}
          >
            {itemCode}
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 8,
            padding: "0 12px 12px",
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: "8px 12px",
              background: "#e2e8f0",
              border: "1px solid #cbd5e1",
              borderRadius: 4,
              cursor: "pointer",
              fontWeight: 600,
              fontSize: 13,
              color: "#475569",
              transition: "all 0.2s",
            }}
            onMouseOver={(e) => {
              e.target.style.background = "#cbd5e1";
            }}
            onMouseOut={(e) => {
              e.target.style.background = "#e2e8f0";
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => {
              onSearch?.();
              onClose?.();
            }}
            style={{
              padding: "8px 12px",
              background: "#3b82f6",
              border: "1px solid #2563eb",
              borderRadius: 4,
              cursor: "pointer",
              fontWeight: 600,
              fontSize: 13,
              color: "#fff",
              transition: "all 0.2s",
            }}
            onMouseOver={(e) => {
              e.target.style.background = "#2563eb";
            }}
            onMouseOut={(e) => {
              e.target.style.background = "#3b82f6";
            }}
          >
            Search
          </button>
        </div>
      </div>
    </div>
  );
}
