import { C, FONT_MONO, FONT_DISPLAY } from "./styles";

export function Badge({ label, color }) {
  const c = color || { fg: C.muted, bg: C.dim };
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.08em",
        padding: "3px 8px",
        borderRadius: 4,
        background: c.bg,
        color: c.fg,
        fontFamily: FONT_MONO,
        textTransform: "uppercase",
        border: `1px solid ${c.fg}22`,
      }}
    >
      {label}
    </span>
  );
}

export function Pill({ label }) {
  return (
    <span
      style={{
        fontSize: 10,
        fontFamily: FONT_MONO,
        letterSpacing: "0.06em",
        padding: "2px 7px",
        borderRadius: 20,
        background: C.dim,
        color: C.muted,
      }}
    >
      {label}
    </span>
  );
}

export function Btn({
  children,
  onClick,
  variant = "primary",
  small,
  disabled,
  loading,
}) {
  const variants = {
    primary: { bg: C.accent, color: "#000", border: "none" },
    danger: { bg: C.red, color: "#fff", border: "none" },
    success: { bg: C.green, color: "#000", border: "none" },
    ghost: { bg: "transparent", color: C.muted, border: `1px solid ${C.border}` },
    warning: { bg: C.amber, color: "#000", border: "none" },
  };
  const v = variants[variant] || variants.primary;
  return (
    <button
      onClick={disabled || loading ? undefined : onClick}
      style={{
        ...v,
        padding: small ? "5px 12px" : "8px 18px",
        borderRadius: 6,
        fontSize: small ? 11 : 12,
        fontFamily: FONT_MONO,
        fontWeight: 600,
        cursor: disabled || loading ? "not-allowed" : "pointer",
        opacity: disabled || loading ? 0.5 : 1,
        letterSpacing: "0.04em",
        transition: "opacity 0.15s",
        whiteSpace: "nowrap",
      }}
    >
      {loading ? "…" : children}
    </button>
  );
}

export function StatCard({ label, value, sub, accent }) {
  return (
    <div
      style={{
        background: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: 10,
        padding: "20px 22px",
        borderTop: accent ? `2px solid ${accent}` : undefined,
      }}
    >
      <div
        style={{
          fontSize: 11,
          color: C.muted,
          fontFamily: FONT_MONO,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          marginBottom: 10,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 28,
          fontWeight: 700,
          color: accent || C.text,
          fontFamily: FONT_DISPLAY,
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      {sub && (
        <div
          style={{
            fontSize: 11,
            color: C.muted,
            marginTop: 6,
            fontFamily: FONT_MONO,
          }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}

export function SectionHead({ title, action }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 16,
        paddingBottom: 12,
        borderBottom: `1px solid ${C.border}`,
      }}
    >
      <span
        style={{
          fontSize: 12,
          fontFamily: FONT_MONO,
          color: C.muted,
          letterSpacing: "0.10em",
          textTransform: "uppercase",
        }}
      >
        {title}
      </span>
      {action}
    </div>
  );
}

export function Alert({ type, msg }) {
  const colors = {
    warn: { bg: C.amberDim, border: C.amber, color: C.amber },
    error: { bg: C.redDim, border: C.red, color: C.red },
  };
  const c = colors[type] || colors.warn;
  return (
    <div
      style={{
        background: c.bg,
        border: `1px solid ${c.border}`,
        borderRadius: 6,
        padding: "8px 14px",
        fontSize: 12,
        color: c.color,
        fontFamily: FONT_MONO,
      }}
    >
      {msg}
    </div>
  );
}

export function Input({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  required,
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      {label && (
        <label
          style={{
            fontSize: 10,
            color: C.muted,
            fontFamily: FONT_MONO,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          {label}
          {required && <span style={{ color: C.red }}> *</span>}
        </label>
      )}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 6,
          color: C.text,
          fontFamily: FONT_MONO,
          fontSize: 12,
          padding: "9px 12px",
          outline: "none",
          width: "100%",
          boxSizing: "border-box",
        }}
      />
    </div>
  );
}

export function Select({ label, value, onChange, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      {label && (
        <label
          style={{
            fontSize: 10,
            color: C.muted,
            fontFamily: FONT_MONO,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          {label}
        </label>
      )}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 6,
          color: C.text,
          fontFamily: FONT_MONO,
          fontSize: 12,
          padding: "9px 12px",
          outline: "none",
          width: "100%",
        }}
      >
        {children}
      </select>
    </div>
  );
}

export function Spinner() {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "40px 0",
        color: C.muted,
        fontFamily: FONT_MONO,
        fontSize: 12,
      }}
    >
      Loading…
    </div>
  );
}

export function Overlay({ children, onClose }) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(0,0,0,0.7)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: 12,
          padding: "28px 28px",
          width: "100%",
          maxWidth: 440,
          boxShadow: "0 24px 60px rgba(0,0,0,0.5)",
        }}
      >
        {children}
      </div>
    </div>
  );
}
