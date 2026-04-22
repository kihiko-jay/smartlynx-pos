import { useState, useEffect } from "react";
import { shellStyles } from "./styles";

export function KPIBox({ label, value, sub, accent = "#155eef", delta }) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div style={shellStyles.statCard(accent, isMobile)}>
      <div
        style={{
          color: "#64748b",
          fontSize: isMobile ? 10 : 11,
          fontWeight: 700,
          letterSpacing: ".06em",
          textTransform: "uppercase",
          marginBottom: 8,
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: isMobile ? 20 : 28, fontWeight: 800, color: "#111827" }}>{value}</div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, flexWrap: "wrap", gap: 4 }}>
        <div style={{ fontSize: isMobile ? 10 : 12, color: "#64748b" }}>{sub}</div>
        {delta && (
          <div style={{ fontSize: isMobile ? 10 : 11, color: "#64748b", fontWeight: 700 }}>{delta}</div>
        )}
      </div>
    </div>
  );
}

export function Section({ title, right, children, style }) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div style={{ ...shellStyles.panel, ...style }}>
      {title && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            ...shellStyles.panelTitle(isMobile),
          }}
        >
          <span>{title}</span>
          {right && <div>{right}</div>}
        </div>
      )}
      <div style={{ padding: isMobile ? "12px 16px" : "20px 24px" }}>{children}</div>
    </div>
  );
}

export function EmptyState({ text = "No data yet." }) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div
      style={{
        textAlign: "center",
        padding: isMobile ? "30px 16px" : "40px 20px",
        color: "#94a3b8",
        fontSize: isMobile ? 12 : 14,
        fontWeight: 500,
      }}
    >
      {text}
    </div>
  );
}

export function TableShell({ headers, children, hideColumns = [] }) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // On mobile with many columns, show fewer columns
  const visibleHeaders = isMobile
    ? headers.filter((h, idx) => !hideColumns.includes(idx))
    : headers;
  const visibleCount = visibleHeaders.length || headers.length;

  return (
    <div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${visibleCount}, minmax(0,1fr))`,
          background: "#edf4ff",
          borderBottom: "1px solid #cbd5e1",
          fontWeight: 700,
          fontSize: isMobile ? 10 : 11,
          color: "#334155",
          textTransform: "uppercase",
          letterSpacing: ".04em",
        }}
      >
        {visibleHeaders.map((h) => (
          <div key={h} style={{ padding: isMobile ? "8px 10px" : "10px 12px" }}>
            {h}
          </div>
        ))}
      </div>
      {children}
    </div>
  );
}

export function Loading() {
  return <EmptyState text="Loading..." />;
}
