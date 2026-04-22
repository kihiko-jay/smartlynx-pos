import { useState } from "react";
import { platformAPI } from "../../api/client";
import { C, FONT_DISPLAY, FONT_MONO } from "./styles";
import { Alert, Input, Btn, SectionHead } from "./UIComponents";

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

export default function RegisterTab({ onDone }) {
  const [form, setForm] = useState({
    store_name: "",
    store_location: "",
    kra_pin: "",
    admin_name: "",
    admin_email: "",
    admin_password: "",
    admin_phone: "",
  });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState(null);

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (
      !form.store_name ||
      !form.admin_name ||
      !form.admin_email ||
      !form.admin_password
    ) {
      setErr("Store name, admin name, email, and password are required.");
      return;
    }
    setLoading(true);
    setErr("");
    try {
      const result = await platformAPI.registerStore(form);
      setSuccess(result);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div
        style={{
          background: C.card,
          border: `1px solid ${C.green}44`,
          borderRadius: 10,
          padding: "28px 24px",
          maxWidth: 520,
        }}
      >
        <div
          style={{
            fontSize: 16,
            fontWeight: 700,
            color: C.green,
            fontFamily: FONT_DISPLAY,
            marginBottom: 16,
          }}
        >
          ✓ Store registered successfully
        </div>
        <DetailGrid
          rows={[
            ["Store name", success.store_name],
            ["Store ID", success.store_id],
            ["Admin email", success.admin_email],
            ["Trial ends", success.trial_ends],
            ["Plan", "Free (14-day trial)"],
          ]}
        />
        <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
          <Btn
            variant="primary"
            onClick={() => {
              setSuccess(null);
              setForm({
                store_name: "",
                store_location: "",
                kra_pin: "",
                admin_name: "",
                admin_email: "",
                admin_password: "",
                admin_phone: "",
              });
            }}
          >
            Register Another
          </Btn>
          <Btn variant="ghost" onClick={onDone}>
            Back to Stores
          </Btn>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 520 }}>
      <div
        style={{
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: 10,
          padding: "22px 24px",
        }}
      >
        <SectionHead title="Store details" />
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Input
            label="Store name *"
            value={form.store_name}
            onChange={set("store_name")}
            placeholder="e.g. Mama Pima Duka — Westlands"
            required
          />
          <Input
            label="Location"
            value={form.store_location}
            onChange={set("store_location")}
            placeholder="e.g. Westlands, Nairobi"
          />
          <Input
            label="KRA PIN"
            value={form.kra_pin}
            onChange={set("kra_pin")}
            placeholder="e.g. P051234567R"
          />
        </div>
      </div>

      <div
        style={{
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: 10,
          padding: "22px 24px",
        }}
      >
        <SectionHead title="Admin account" />
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Input
            label="Full name *"
            value={form.admin_name}
            onChange={set("admin_name")}
            placeholder="e.g. Jane Wanjiku"
            required
          />
          <Input
            label="Email *"
            type="email"
            value={form.admin_email}
            onChange={set("admin_email")}
            placeholder="admin@theirdomain.com"
            required
          />
          <Input
            label="Phone"
            value={form.admin_phone}
            onChange={set("admin_phone")}
            placeholder="e.g. 0712345678"
          />
          <Input
            label="Password *"
            type="password"
            value={form.admin_password}
            onChange={set("admin_password")}
            placeholder="Min 8 characters"
            required
          />
        </div>
      </div>

      <div
        style={{
          background: C.amberDim,
          border: `1px solid ${C.amber}44`,
          borderRadius: 8,
          padding: "10px 14px",
          fontSize: 11,
          color: C.amber,
          fontFamily: FONT_MONO,
        }}
      >
        The store starts on a free 14-day trial. Use the Stores tab to activate a
        paid plan after registration.
      </div>

      {err && <Alert type="error" msg={err} />}

      <Btn variant="primary" onClick={submit} loading={loading}>
        Register Store & Create Admin Account
      </Btn>
    </div>
  );
}
