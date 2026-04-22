/**
 * ExpenseVoucherList — paginated, filterable list of expense vouchers.
 * Features: live list, show-voided toggle, void with reason (manager+), totals footer.
 */
import { useEffect, useState, useCallback } from "react";
import { expensesAPI, fmtKES, getSession } from "../../api/client";
import { shellStyles } from "../backoffice/styles";
import { Section, EmptyState } from "../backoffice/UIComponents";

const PM_LABELS = { cash:"Cash", mpesa:"M-PESA", card:"Card", bank:"Bank Transfer", cheque:"Cheque" };
const fmt = (v) => fmtKES(v ?? 0);

function useMobile() {
  const [m, setM] = useState(typeof window !== "undefined" && window.innerWidth < 768);
  useEffect(() => { const h = () => setM(window.innerWidth < 768); window.addEventListener("resize", h); return () => window.removeEventListener("resize", h); }, []);
  return m;
}

function canVoid(role) { return ["manager","admin","platform_owner"].includes(role?.toLowerCase()); }

function VoidModal({ voucher, onClose, onDone }) {
  const isMobile = useMobile();
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const handleVoid = async () => {
    if (!reason.trim()) { setError("Void reason is required."); return; }
    setLoading(true); setError(null);
    try { await expensesAPI.void(voucher.id, reason); onDone(); }
    catch (e) { setError(e.message || "Failed to void voucher"); }
    finally { setLoading(false); }
  };
  return (
    <div style={{ position:"fixed",inset:0,background:"rgba(0,0,0,0.55)",zIndex:1100,display:"flex",alignItems:"center",justifyContent:"center",padding:16 }}>
      <div style={{ background:"#fff",borderRadius:14,padding:isMobile?20:28,width:"100%",maxWidth:420,boxShadow:"0 8px 32px rgba(0,0,0,0.22)" }}>
        <div style={{ fontWeight:800,fontSize:16,color:"#dc2626",marginBottom:4 }}>Void Expense Voucher</div>
        <div style={{ fontSize:12,color:"#64748b",marginBottom:20 }}><strong>{voucher.voucher_number}</strong> · {fmt(voucher.amount)} · {voucher.expense_date}</div>
        <div style={{ marginBottom:16 }}>
          <label style={{ fontSize:11,fontWeight:700,color:"#334155",display:"block",marginBottom:6,textTransform:"uppercase" }}>Void Reason *</label>
          <textarea value={reason} onChange={e=>setReason(e.target.value)} rows={3} placeholder="Required..." style={{ ...shellStyles.searchInput,width:"100%",padding:"9px 12px",resize:"vertical" }} />
        </div>
        {error && <div style={{ background:"#fef2f2",border:"1px solid #fca5a5",borderRadius:8,padding:"8px 12px",marginBottom:12,fontSize:12,color:"#dc2626" }}>{error}</div>}
        <div style={{ display:"flex",gap:10 }}>
          <button onClick={handleVoid} disabled={loading} style={{ flex:1,padding:"10px 0",borderRadius:8,border:"none",background:loading?"#94a3b8":"#dc2626",color:"#fff",fontWeight:700,fontSize:14,cursor:"pointer" }}>{loading?"Voiding...":"Confirm Void"}</button>
          <button onClick={onClose} disabled={loading} style={{ padding:"10px 20px",borderRadius:8,border:"1px solid #e2e8f0",background:"#f8fafc",cursor:"pointer",color:"#475569",fontWeight:600 }}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export default function ExpenseVoucherList({ onCreateNew, refreshKey }) {
  const isMobile = useMobile();
  const session = getSession();
  const [vouchers, setVouchers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showVoided, setShowVoided] = useState(false);
  const [voidTarget, setVoidTarget] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { const data = await expensesAPI.list(); setVouchers(Array.isArray(data) ? data : []); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [refreshKey]);

  useEffect(() => { load(); }, [load]);

  const visible = vouchers.filter(v => showVoided ? v.is_void : !v.is_void);
  const totalActive = vouchers.filter(v => !v.is_void).reduce((s,v) => s + parseFloat(v.amount||0), 0);

  return (
    <>
      <Section
        title="Expense Vouchers"
        right={
          <div style={{ display:"flex",gap:8,alignItems:"center",flexWrap:"wrap" }}>
            <button onClick={()=>setShowVoided(!showVoided)} style={{ padding:"4px 12px",borderRadius:20,border:"1px solid",fontSize:11,fontWeight:700,cursor:"pointer",background:showVoided?"#dc2626":"#f8fafc",color:showVoided?"#fff":"#475569",borderColor:showVoided?"#dc2626":"#cbd5e1" }}>
              {showVoided?"Showing Voided":"Show Voided"}
            </button>
            <button onClick={onCreateNew} style={{ ...shellStyles.smallButton(isMobile),background:"#1b6cff",color:"#fff",borderColor:"#1b6cff" }}>+ New Voucher</button>
          </div>
        }
      >
        {loading && <EmptyState text="Loading vouchers..." />}
        {error   && <EmptyState text={`Error: ${error}`} />}
        {!loading && !error && visible.length === 0 && <EmptyState text={showVoided?"No voided vouchers.":"No expense vouchers yet. Click '+ New Voucher' to record an expense."} />}
        {!loading && !error && visible.length > 0 && (
          <>
            <div style={{ overflowX:"auto" }}>
              <table style={{ width:"100%",borderCollapse:"collapse",fontSize:isMobile?11:13 }}>
                <thead>
                  <tr style={{ background:"#edf4ff",borderBottom:"2px solid #bfdbfe" }}>
                    {["Voucher #","Date","Account","Amount","Method","Payee","Reference",""].map(h=>(
                      <th key={h} style={{ padding:isMobile?"6px 8px":"9px 12px",textAlign:h==="Amount"?"right":"left",fontWeight:700,fontSize:11,textTransform:"uppercase",color:"#334155",whiteSpace:"nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visible.map((v,i)=>(
                    <tr key={v.id} style={{ background:v.is_void?"#fef2f2":i%2===0?"#fff":"#f8fafc",borderBottom:"1px solid #e2e8f0",opacity:v.is_void?0.7:1 }}>
                      <td style={{ padding:isMobile?"6px 8px":"8px 12px",fontFamily:"monospace",fontWeight:700,color:"#1b6cff" }}>
                        {v.voucher_number}
                        {v.is_void && <span style={{ marginLeft:6,fontSize:10,fontWeight:700,color:"#dc2626",background:"#fee2e2",borderRadius:4,padding:"1px 5px" }}>VOID</span>}
                      </td>
                      <td style={{ padding:isMobile?"6px 8px":"8px 12px",color:"#64748b" }}>{v.expense_date}</td>
                      <td style={{ padding:isMobile?"6px 8px":"8px 12px",fontSize:12 }}>
                        {v.account?.name||`Account #${v.account_id}`}
                        {v.account?.code && <span style={{ marginLeft:6,fontSize:10,color:"#94a3b8",fontFamily:"monospace" }}>{v.account.code}</span>}
                      </td>
                      <td style={{ padding:isMobile?"6px 8px":"8px 12px",textAlign:"right",fontFamily:"monospace",fontWeight:600 }}>{fmt(v.amount)}</td>
                      <td style={{ padding:isMobile?"6px 8px":"8px 12px",color:"#64748b" }}>{PM_LABELS[v.payment_method]||v.payment_method}</td>
                      <td style={{ padding:isMobile?"6px 8px":"8px 12px" }}>{v.payee||"—"}</td>
                      <td style={{ padding:isMobile?"6px 8px":"8px 12px",color:"#94a3b8",fontSize:12 }}>{v.reference||"—"}</td>
                      <td style={{ padding:isMobile?"6px 8px":"8px 12px" }}>
                        {!v.is_void && canVoid(session?.role) && (
                          <button onClick={()=>setVoidTarget(v)} style={{ ...shellStyles.smallButton(isMobile),padding:"2px 10px",minHeight:26,fontSize:11,color:"#dc2626",borderColor:"#fca5a5" }}>Void</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!showVoided && (
              <div style={{ marginTop:12,display:"flex",justifyContent:"flex-end",gap:24,padding:"10px 16px",background:"#f8fafc",borderRadius:8,fontSize:13,fontWeight:700,color:"#1e293b" }}>
                <span style={{ color:"#64748b",fontWeight:400 }}>{visible.length} voucher{visible.length!==1?"s":""}</span>
                <span>Total: <span style={{ color:"#dc2626" }}>{fmt(totalActive)}</span></span>
              </div>
            )}
          </>
        )}
      </Section>
      {voidTarget && <VoidModal voucher={voidTarget} onClose={()=>setVoidTarget(null)} onDone={()=>{setVoidTarget(null);load();}} />}
    </>
  );
}
