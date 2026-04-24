import { useEffect, useMemo, useState } from "react";
import { etimsAPI, fmtKES, reportsAPI } from "../../api/client";
import { shellStyles } from "./styles";
import { EmptyState, Section } from "./UIComponents";

function normalizeRows(report) {
  if (Array.isArray(report)) return report;
  if (Array.isArray(report?.items)) return report.items;
  if (Array.isArray(report?.lines)) return report.lines;
  if (Array.isArray(report?.products)) return report.products;
  if (Array.isArray(report?.results)) return report.results;
  return [];
}

function exportBlob(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function rowsToCsv(rows) {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const esc = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  return [headers.join(","), ...rows.map((row) => headers.map((h) => esc(row[h])).join(","))].join("\n");
}

export default function ReportsTab() {
  const [activeReport, setActiveReport] = useState("ztape");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [etimsPending, setEtimsPending] = useState(null);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);
  const [error, setError] = useState("");

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const loadReport = async (type) => {
    setLoading(true);
    setReport(null);
    setError("");
    try {
      switch (type) {
        case "ztape":
          setReport(await reportsAPI.zTape());
          break;
        case "weekly":
          setReport(await reportsAPI.weekly());
          break;
        case "top":
          setReport(await reportsAPI.topProducts());
          break;
        case "inventory":
          setReport(await reportsAPI.lowStock());
          break;
        case "vat":
          {
            const now = new Date();
            setReport(await reportsAPI.vat(now.getMonth() + 1, now.getFullYear()));
          }
          break;
        default:
          setReport(await reportsAPI.zTape());
      }
      try {
        setEtimsPending(await etimsAPI.pending?.());
      } catch {
        setEtimsPending(null);
      }
    } catch (err) {
      setError(err.message || "Failed to load report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport(activeReport);
  }, [activeReport]);

  const rows = useMemo(() => normalizeRows(report), [report]);
  const summary = useMemo(() => {
    if (!report || typeof report !== "object") return [];
    return Object.entries(report)
      .filter(([, value]) => !Array.isArray(value) && (typeof value === "string" || typeof value === "number" || typeof value === "boolean" || value == null))
      .slice(0, 8);
  }, [report]);

  const exportJson = () => exportBlob(`smartlynx-${activeReport}.json`, JSON.stringify(report, null, 2), "application/json");
  const exportCsv = () => exportBlob(`smartlynx-${activeReport}.csv`, rowsToCsv(rows), "text/csv;charset=utf-8");

  const exportPdf = async () => {
  try {
    setError("");
    const reportTypeMap = {
      ztape: "ztape",
      weekly: "weekly",
      top: "top-products",
      inventory: "low-stock",
      vat: "vat"
    };
    const reportType = reportTypeMap[activeReport];
    const now = new Date();
    
    let params = { download: true };
    
    // Add date parameters for reports that need them
    if (activeReport === "vat") {
      params.month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    } else if (activeReport === "ztape") {
      params.report_date = now.toISOString().split("T")[0];
    }
    
    let result;
    switch (activeReport) {
      case "ztape":
        result = await reportsAPI.downloadZtapePDF(params);
        break;
      case "weekly":
        result = await reportsAPI.downloadWeeklyPDF(params);
        break;
      case "vat":
        result = await reportsAPI.downloadVatPDF(params);
        break;
      case "top":
        result = await reportsAPI.downloadTopProductsPDF(params);
        break;
      case "inventory":
        result = await reportsAPI.downloadLowStockPDF(params);
        break;
      default:
        result = await reportsAPI.downloadZtapePDF(params);
    }
    
    if (!result?.blob) {
      throw new Error("No PDF data returned");
    }
    
    const blobUrl = URL.createObjectURL(result.blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = `smartlynx-${activeReport}-${new Date().toISOString().split("T")[0]}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // Clean up the blob URL after download
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
  } catch (err) {
    setError(`PDF export failed: ${err.message}`);
  }
};

  return (
    <div style={{ display: "grid", gap: isMobile ? 12 : 16 }}>
      <Section
        title="Reports Center"
        right={
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(3, 1fr)" : "repeat(7, auto)", gap: isMobile ? 4 : 8 }}>
            {[ ["ztape","Z Tape"], ["weekly","Weekly"], ["top","Top"], ["inventory","Stock"], ["vat","VAT"] ].map(([key, label]) => (
              <button key={key} onClick={() => setActiveReport(key)} style={activeReport === key ? shellStyles.primaryButton(isMobile) : shellStyles.smallButton(isMobile)}>{isMobile ? label.slice(0, 4) : label}</button>
            ))}
            <button onClick={exportJson} style={shellStyles.smallButton(isMobile)} disabled={!report}>JSON</button>
            <button onClick={exportCsv} style={shellStyles.smallButton(isMobile)} disabled={!rows.length}>CSV</button>
            <button onClick={exportPdf} style={shellStyles.smallButton(isMobile)} disabled={!report}>PDF</button>
          </div>
        }
      >
        {loading ? <EmptyState text="Loading report..." /> : null}
        {error ? <div style={{ padding: 12, color: "#b42318", fontWeight: 700 }}>{error}</div> : null}
        {!loading && !error && !report ? <EmptyState text="No report data available." /> : null}
        {!loading && !!report ? (
          <div style={{ display: "grid", gap: 12, padding: 12 }}>
            {summary.length ? (
              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(4, minmax(0,1fr))", gap: 10 }}>
                {summary.map(([key, value]) => (
                  <div key={key} style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: 8, padding: 12 }}>
                    <div style={{ color: "#64748b", fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>{key.replaceAll("_", " ")}</div>
                    <div style={{ marginTop: 6, fontSize: 16, fontWeight: 800 }}>{typeof value === "number" && key.toLowerCase().includes("amount") ? fmtKES(value) : String(value)}</div>
                  </div>
                ))}
              </div>
            ) : null}
            {rows.length ? (
              <div style={{ border: "1px solid #cbd5e1", borderRadius: 8, overflow: "auto", background: "#fff" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: isMobile ? 11 : 12 }}>
                  <thead>
                    <tr style={{ background: "#edf4ff" }}>
                      {Object.keys(rows[0]).map((key) => <th key={key} style={{ textAlign: "left", padding: "10px 12px", borderBottom: "1px solid #cbd5e1" }}>{key}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, idx) => (
                      <tr key={idx} style={{ background: idx % 2 ? "#f8fbff" : "#fff" }}>
                        {Object.keys(rows[0]).map((key) => <td key={key} style={{ padding: "10px 12px", borderTop: "1px solid #eef2f6" }}>{typeof row[key] === "number" && key.toLowerCase().includes("amount") ? fmtKES(row[key]) : String(row[key] ?? "")}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <pre style={{ background: "#0f1724", color: "#dbeafe", padding: isMobile ? 10 : 16, borderRadius: 8, overflow: "auto", fontSize: isMobile ? 10 : 12 }}>{JSON.stringify(report, null, 2)}</pre>
            )}
            {etimsPending ? <div style={{ color: "#b45309", fontWeight: 700, fontSize: isMobile ? 11 : 12 }}>eTIMS pending items: {etimsPending.count ?? 0}</div> : null}
          </div>
        ) : null}
      </Section>
    </div>
  );
}
