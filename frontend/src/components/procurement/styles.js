// ── Shared style tokens ────────────────────────────────────────────────────
export const MONO  = "'DM Mono',monospace";
export const SYNE  = "'Syne',sans-serif";
export const SAND  = "#f5f1e8";
export const BONE  = "#e8e3d8";
export const INK   = "#1a1a1a";
export const MUTED = "#888";
export const AMBER = "#f5a623";
export const GREEN = "#16a34a";
export const RED   = "#dc2626";
export const BLUE  = "#2563eb";

export const STATUS_COLOR = {
  draft:              { bg:"#f9f5f0", fg:"#92400e" },
  submitted:          { bg:"#eff6ff", fg:BLUE },
  approved:           { bg:"#f0fdf4", fg:GREEN },
  partially_received: { bg:"#fefce8", fg:"#a16207" },
  fully_received:     { bg:"#f0fdf4", fg:GREEN },
  closed:             { bg:"#f1f5f9", fg:"#475569" },
  cancelled:          { bg:"#fef2f2", fg:RED },
  posted:             { bg:"#f0fdf4", fg:GREEN },
  unmatched:          { bg:"#fef2f2", fg:RED },
  partial:            { bg:"#fefce8", fg:"#a16207" },
  matched:            { bg:"#f0fdf4", fg:GREEN },
  disputed:           { bg:"#fef2f2", fg:RED },
};

export const UNIT_TYPES = ["unit","pack","box","carton","case","dozen","bale","sack","roll","other"];
export const fmtKES = (v) => {
  const num = parseFloat(v || 0) || 0;
  // Display exact value from database - no rounding
  return `KES ${num.toLocaleString("en-KE", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
};
export const today  = () => new Date().toISOString().slice(0,10);
