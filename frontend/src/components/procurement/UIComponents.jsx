import { STATUS_COLOR, MONO, INK, MUTED, RED, BONE, SYNE } from "./styles";

export function Badge({ status }) {
  const s = STATUS_COLOR[status] || { bg:"#f1f5f9", fg:"#555" };
  return (
    <span style={{ fontSize:10, fontWeight:600, padding:"2px 8px", borderRadius:20,
                   background:s.bg, color:s.fg, fontFamily:MONO, textTransform:"uppercase",
                   letterSpacing:"0.06em" }}>
      {status?.replace(/_/g," ")}
    </span>
  );
}

export function Btn({ children, onClick, variant="primary", small, disabled, style={} }) {
  const base = { padding: small?"4px 12px":"8px 18px", borderRadius:6, fontFamily:MONO,
                 fontSize: small?11:12, cursor: disabled?"not-allowed":"pointer",
                 border:"none", fontWeight:500, opacity: disabled?0.5:1, ...style };
  const themes = {
    primary:  { background:INK, color:"#fff" },
    secondary:{ background:"#fff", color:INK, border:`1px solid ${BONE}` },
    danger:   { background:"#dc2626",   color:"#fff" },
    success:  { background:"#16a34a", color:"#fff" },
  };
  return <button onClick={disabled?undefined:onClick} style={{...base,...themes[variant]}}>{children}</button>;
}

export function Input({ label, ...props }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
      {label && <label style={{ fontSize:11, color:MUTED, fontFamily:MONO }}>{label}</label>}
      <input style={{ padding:"7px 10px", borderRadius:6, border:`1px solid ${BONE}`,
                      fontFamily:MONO, fontSize:12, background:"#fff",
                      outline:"none", width:"100%" }} {...props}/>
    </div>
  );
}

export function Select({ label, children, ...props }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
      {label && <label style={{ fontSize:11, color:MUTED, fontFamily:MONO }}>{label}</label>}
      <select style={{ padding:"7px 10px", borderRadius:6, border:`1px solid ${BONE}`,
                       fontFamily:MONO, fontSize:12, background:"#fff",
                       outline:"none", width:"100%" }} {...props}>
        {children}
      </select>
    </div>
  );
}

export function Card({ children, style={} }) {
  return <div style={{ background:"#fff", border:`1px solid ${BONE}`, borderRadius:10,
                       padding:"20px 24px", ...style }}>{children}</div>;
}

export function SectionHead({ title, sub, action }) {
  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between",
                  marginBottom:20 }}>
      <div>
        <div style={{ fontFamily:SYNE, fontWeight:800, fontSize:20, color:INK }}>{title}</div>
        {sub && <div style={{ fontSize:11, color:MUTED, marginTop:3, fontFamily:MONO }}>{sub}</div>}
      </div>
      {action}
    </div>
  );
}

export function Err({ msg }) {
  if (!msg) return null;
  return <div style={{ background:"#fef2f2", color:RED, border:`1px solid #fecaca`,
                       borderRadius:6, padding:"8px 12px", fontSize:12, fontFamily:MONO,
                       marginBottom:12 }}>{msg}</div>;
}

export function Loading() {
  return <div style={{ textAlign:"center", padding:60, color:MUTED, fontFamily:MONO }}>Loading…</div>;
}
