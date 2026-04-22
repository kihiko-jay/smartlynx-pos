import { useState, useEffect, useCallback } from "react";
import { platformAPI } from "../../api/client";
import { C, FONT_DISPLAY, FONT_MONO, PLAN_COLOR, STATUS_COLOR } from "./styles";
import {
  Badge,
  Pill,
  Btn,
  Select,
  Input,
  Alert,
  Spinner,
  Overlay,
} from "./UIComponents";

export default function StoresTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState({ plan: "", status: "" });
  const [acting, setActing] = useState({});
  const [modal, setModal] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    const params = {};
    if (filter.plan) params.plan = filter.plan;
    if (filter.status) params.status = filter.status;
    platformAPI
      .listStores(params)
      .then(setData)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const action = async (storeId, fn, label) => {
    setActing((a) => ({ ...a, [storeId]: label }));
    try {
      await fn();
      load();
    } catch (e) {
      alert(`Error: ${e.message}`);
    } finally {
      setActing((a) => {
        const n = { ...a };
        delete n[storeId];
        return n;
      });
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Filters */}
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <Select
          value={filter.plan}
          onChange={(v) => setFilter((f) => ({ ...f, plan: v }))}
        >
          <option value="">All plans</option>
          <option value="free">Free</option>
          <option value="starter">Starter</option>
          <option value="growth">Growth</option>
          <option value="pro">Pro</option>
        </Select>
        <Select
          value={filter.status}
          onChange={(v) => setFilter((f) => ({ ...f, status: v }))}
        >
          <option value="">All statuses</option>
          <option value="trialing">Trialing</option>
          <option value="active">Active</option>
          <option value="cancelled">Cancelled</option>
          <option value="expired">Expired</option>
        </Select>
        <Btn variant="ghost" small onClick={load}>
          Refresh
        </Btn>
        {data && <Pill label={`${data.total} stores`} />}
      </div>

      {err && <Alert type="error" msg={err} />}

      {loading ? (
        <Spinner />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {(data?.stores || []).map((s) => (
            <StoreRow
              key={s.store_id}
              store={s}
              acting={acting[s.store_id]}
              onActivate={() => setModal({ store: s, type: "activate" })}
              onSuspend={() => setModal({ store: s, type: "suspend" })}
              onReinstate={() =>
                action(
                  s.store_id,
                  () => platformAPI.reinstateStore(s.store_id),
                  "Reinstating…"
                )
              }
            />
          ))}
          {data?.stores?.length === 0 && (
            <div
              style={{
                color: C.muted,
                fontFamily: FONT_MONO,
                fontSize: 12,
                textAlign: "center",
                padding: "40px 0",
              }}
            >
              No stores match these filters.
            </div>
          )}
        </div>
      )}

      {/* Activate modal */}
      {modal?.type === "activate" && (
        <ActivateModal
          store={modal.store}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            load();
          }}
        />
      )}

      {/* Suspend modal */}
      {modal?.type === "suspend" && (
        <SuspendModal
          store={modal.store}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function StoreRow({ store: s, acting, onActivate, onSuspend, onReinstate }) {
  const [open, setOpen] = useState(false);
  const pc = PLAN_COLOR[s.plan] || { fg: C.muted, bg: C.dim };
  const sc = STATUS_COLOR[s.sub_status] || STATUS_COLOR.expired;

  return (
    <div
      style={{
        background: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: 10,
        overflow: "hidden",
        borderLeft: s.is_active ? `3px solid ${sc.fg}` : `3px solid ${C.red}`,
      }}
    >
      {/* Row header */}
      <div
        onClick={() => setOpen((o) => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "14px 18px",
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        {/* Store ID badge */}
        <span
          style={{
            fontFamily: FONT_MONO,
            fontSize: 11,
            color: C.muted,
            background: C.surface,
            padding: "2px 7px",
            borderRadius: 4,
            border: `1px solid ${C.border}`,
          }}
        >
          #{s.store_id}
        </span>

        {/* Name + location */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: C.text,
              fontFamily: FONT_DISPLAY,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {s.name}
          </div>
          {s.location && (
            <div
              style={{
                fontSize: 11,
                color: C.muted,
                fontFamily: FONT_MONO,
              }}
            >
              {s.location}
            </div>
          )}
        </div>

        {/* Badges */}
        <div
          style={{
            display: "flex",
            gap: 6,
            alignItems: "center",
            flexShrink: 0,
          }}
        >
          <Badge label={s.plan} color={pc} />
          <Badge label={s.sub_status} color={sc} />
          {s.days_left !== null && <Pill label={`${s.days_left}d left`} />}
          <Pill label={`${s.employee_count} staff`} />
        </div>

        <span style={{ color: C.muted, fontSize: 11, marginLeft: 4 }}>
          {open ? "▲" : "▼"}
        </span>
      </div>

      {/* Expanded detail */}
      {open && (
        <div
          style={{
            borderTop: `1px solid ${C.border}`,
            padding: "14px 18px",
            display: "flex",
            gap: 20,
            flexWrap: "wrap",
          }}
        >
          {/* Details grid */}
          <div style={{ flex: "1 1 280px" }}>
            <DetailGrid
              rows={[
                ["KRA PIN", s.kra_pin || "—"],
                ["Phone", s.phone || "—"],
                ["Email", s.email || "—"],
                [
                  "Trial ends",
                  s.trial_ends
                    ? new Date(s.trial_ends).toLocaleDateString("en-KE")
                    : "—",
                ],
                [
                  "Sub ends",
                  s.sub_ends
                    ? new Date(s.sub_ends).toLocaleDateString("en-KE")
                    : "—",
                ],
                [
                  "Registered",
                  s.registered
                    ? new Date(s.registered).toLocaleDateString("en-KE")
                    : "—",
                ],
                ["Is active", s.is_active ? "Yes" : "No"],
              ]}
            />
          </div>

          {/* Action buttons */}
          <div
            style={{
              display: "flex",
              gap: 8,
              alignItems: "flex-start",
              flexWrap: "wrap",
            }}
          >
            {s.is_active && s.sub_status !== "active" && (
              <Btn
                variant="success"
                small
                onClick={onActivate}
                loading={acting === "Activating…"}
              >
                Activate
              </Btn>
            )}
            {s.is_active && s.sub_status === "active" && (
              <Btn
                variant="success"
                small
                onClick={onActivate}
                loading={acting === "Activating…"}
              >
                Extend / Change Plan
              </Btn>
            )}
            {s.is_active && (
              <Btn
                variant="danger"
                small
                onClick={onSuspend}
                loading={acting === "Suspending…"}
              >
                Suspend
              </Btn>
            )}
            {!s.is_active && (
              <Btn
                variant="warning"
                small
                onClick={onReinstate}
                loading={acting === "Reinstating…"}
              >
                Reinstate (14-day trial)
              </Btn>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DetailGrid({ rows }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gap: "6px 16px",
      }}
    >
      {rows.map(([k, v]) => (
        <div key={k}>
          <span
            style={{
              fontSize: 11,
              color: C.muted,
              fontFamily: FONT_MONO,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            {k}
          </span>
        </div>
      ))}
      {rows.map(([k, v]) => (
        <div key={k}>
          <span
            style={{
              fontSize: 12,
              color: C.text,
              fontFamily: FONT_MONO,
            }}
          >
            {v}
          </span>
        </div>
      ))}
    </div>
  );
}

function ActivateModal({ store, onClose, onDone }) {
  const [plan, setPlan] = useState("starter");
  const [months, setMonths] = useState("1");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setLoading(true);
    setErr("");
    try {
      await platformAPI.activateStore(store.store_id, plan, parseInt(months));
      onDone();
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Overlay onClose={onClose}>
      <div
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 16,
          fontWeight: 700,
          color: C.text,
          marginBottom: 4,
        }}
      >
        Activate Store
      </div>
      <div
        style={{
          fontSize: 12,
          color: C.muted,
          fontFamily: FONT_MONO,
          marginBottom: 20,
        }}
      >
        {store.name}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <Select label="Plan" value={plan} onChange={setPlan}>
          <option value="starter">Starter — KES 1,500/mo</option>
          <option value="growth">Growth — KES 3,500/mo</option>
          <option value="pro">Pro — KES 7,500/mo</option>
        </Select>
        <Select label="Months" value={months} onChange={setMonths}>
          {[1, 2, 3, 6, 12].map((m) => (
            <option key={m} value={m}>
              {m} month{m > 1 ? "s" : ""}
            </option>
          ))}
        </Select>
        {err && <Alert type="error" msg={err} />}
        <div
          style={{
            display: "flex",
            gap: 10,
            justifyContent: "flex-end",
            marginTop: 8,
          }}
        >
          <Btn variant="ghost" onClick={onClose}>
            Cancel
          </Btn>
          <Btn variant="success" onClick={submit} loading={loading}>
            Activate
          </Btn>
        </div>
      </div>
    </Overlay>
  );
}

function SuspendModal({ store, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    if (!reason.trim()) {
      setErr("Please provide a reason.");
      return;
    }
    setLoading(true);
    setErr("");
    try {
      await platformAPI.suspendStore(store.store_id, reason.trim());
      onDone();
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Overlay onClose={onClose}>
      <div
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 16,
          fontWeight: 700,
          color: C.red,
          marginBottom: 4,
        }}
      >
        Suspend Store
      </div>
      <div
        style={{
          fontSize: 12,
          color: C.muted,
          fontFamily: FONT_MONO,
          marginBottom: 20,
        }}
      >
        {store.name}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <Input
          label="Reason *"
          value={reason}
          onChange={setReason}
          placeholder="e.g. Non-payment, Terms violation…"
          required
        />
        {err && <Alert type="error" msg={err} />}
        <div
          style={{
            display: "flex",
            gap: 10,
            justifyContent: "flex-end",
            marginTop: 8,
          }}
        >
          <Btn variant="ghost" onClick={onClose}>
            Cancel
          </Btn>
          <Btn variant="danger" onClick={submit} loading={loading}>
            Suspend Store
          </Btn>
        </div>
      </div>
    </Overlay>
  );
}
