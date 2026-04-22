import { useState, useEffect } from "react";
import { fmtKES } from "../../api/client";

export default function TotalsDisplay({ subtotalExVat, vatAmount, total }) {
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const gridColumns = isMobile ? "1fr" : "1fr 1fr 1fr";
  const fontSize = isMobile ? { label: 11, normal: 18, total: 28 } : { label: 12, normal: 28, total: 42 };
  const padding = isMobile ? 10 : 16;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: gridColumns,
        gap: isMobile ? 6 : 10,
      }}
    >
      {[
        ["Sub Total", subtotalExVat],
        ["Sales Tax", vatAmount],
        ["Total", total],
      ].map(([label, value]) => {
        const isTotal = label === "Total";
        return (
          <div
            key={label}
            className="rms-panel"
            style={{
              background: isTotal
                ? "linear-gradient(180deg, #dceeff 0%, #c6defd 100%)"
                : undefined,
            }}
          >
            <div className="rms-title" style={{ fontSize: fontSize.label }}>{label}</div>
            <div
              style={{
                padding,
                textAlign: "center",
                fontSize: isTotal ? fontSize.total : fontSize.normal,
                fontWeight: 800,
                color: isTotal ? "#0b5ed7" : "#111827",
              }}
            >
              {fmtKES(value)}
            </div>
          </div>
        );
      })}
    </div>
  );
}