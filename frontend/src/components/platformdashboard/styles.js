// Design tokens and color palettes for Platform Dashboard
export const FONT_DISPLAY = "'Clash Display', 'Cabinet Grotesk', 'DM Sans', sans-serif";
export const FONT_MONO = "'JetBrains Mono', 'Fira Code', 'Courier New', monospace";

export const C = {
  bg: "#080b0f",
  surface: "#0d1117",
  card: "#111820",
  border: "#1a2332",
  borderHi: "#243040",
  text: "#e2eaf5",
  muted: "#4a6280",
  dim: "#2a3a50",
  accent: "#00d4ff",
  accentDim: "#003d4d",
  green: "#00c97a",
  greenDim: "#00311e",
  amber: "#f5a623",
  amberDim: "#3d2800",
  red: "#ff4757",
  redDim: "#3d0d13",
  purple: "#a78bfa",
  purpleDim: "#2d1f5e",
};

export const PLAN_COLOR = {
  free: { fg: C.muted, bg: C.dim },
  starter: { fg: C.green, bg: C.greenDim },
  growth: { fg: C.accent, bg: C.accentDim },
  pro: { fg: C.purple, bg: C.purpleDim },
};

export const STATUS_COLOR = {
  trialing: { fg: C.amber, bg: C.amberDim },
  active: { fg: C.green, bg: C.greenDim },
  cancelled: { fg: C.red, bg: C.redDim },
  expired: { fg: C.muted, bg: C.dim },
  suspended: { fg: C.red, bg: C.redDim },
};
