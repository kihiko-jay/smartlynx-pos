/**
 * PlatformDashboard.jsx — SmartSmartlynx v4.3
 *
 * Exclusive to PLATFORM_OWNER role.
 * Platform-wide metrics, store management, and payment tracking.
 *
 * Sub-screens (tabs):
 *   - Overview      | Key metrics, plan breakdown, alerts
 *   - Stores        | Full store list with actions (activate/suspend/reinstate)
 *   - Payments      | M-PESA subscription payment history
 *   - Register      | Onboard a new store from this UI
 */

import { useState, useEffect } from "react";
import { authAPI, clearSession, getSession, sessionHelpers } from "../api/client";
import {
  OverviewTab,
  StoresTab,
  PaymentsTab,
  RegisterTab,
  FONT_DISPLAY,
  FONT_MONO,
  C,
} from "../components/platformdashboard";

const TABS = ["Overview", "Stores", "Payments", "Register Store"];

export default function PlatformDashboard({ onLogout }) {
  const [tab, setTab] = useState("Overview");
  const session = getSession();

  const handleLogout = async () => {
    try {
      const tokens = await sessionHelpers.getTokens();
      if (tokens.refreshToken) {
        try {
          await authAPI.logout(tokens.refreshToken);
        } catch (err) {
          console.warn("Failed to revoke token server-side:", err.message);
        }
      }
    } finally {
      await clearSession();
      onLogout?.();
    }
  };

  const renderTab = () => {
    switch (tab) {
      case "Overview":
        return <OverviewTab />;
      case "Stores":
        return <StoresTab />;
      case "Payments":
        return <PaymentsTab />;
      case "Register Store":
        return <RegisterTab onDone={() => setTab("Stores")} />;
      default:
        return <OverviewTab />;
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: C.bg,
        color: C.text,
        fontFamily: FONT_MONO,
      }}
    >
      {/* Google Fonts */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
        * { box-sizing: border-box; }
        select option { background: #111820; color: #e2eaf5; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #080b0f; }
        ::-webkit-scrollbar-thumb { background: #1a2332; border-radius: 3px; }
      `}</style>

      {/* Top bar */}
      <div
        style={{
          background: C.surface,
          borderBottom: `1px solid ${C.border}`,
          padding: "0 28px",
          display: "flex",
          alignItems: "center",
          height: 52,
          position: "sticky",
          top: 0,
          zIndex: 100,
        }}
      >
        {/* Logo mark */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 32 }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              background: `linear-gradient(135deg, ${C.accent}, ${C.purple})`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <span
              style={{
                fontSize: 12,
                fontWeight: 800,
                color: "#000",
                fontFamily: FONT_DISPLAY,
              }}
            >
              D
            </span>
          </div>
          <div>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: C.text,
                fontFamily: FONT_DISPLAY,
                letterSpacing: "0.04em",
              }}
            >
              Smartlynx
            </div>
            <div
              style={{
                fontSize: 9,
                color: C.accent,
                fontFamily: FONT_MONO,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              }}
            >
              Platform Control
            </div>
          </div>
        </div>

        {/* Tab nav */}
        <nav style={{ display: "flex", gap: 2, flex: 1 }}>
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                background: tab === t ? C.accentDim : "transparent",
                border: "none",
                color: tab === t ? C.accent : C.muted,
                fontFamily: FONT_MONO,
                fontSize: 11,
                fontWeight: tab === t ? 600 : 400,
                padding: "6px 14px",
                borderRadius: 5,
                cursor: "pointer",
                letterSpacing: "0.05em",
                transition: "all 0.15s",
              }}
            >
              {t}
            </button>
          ))}
        </nav>

        {/* Right side: owner info + logout */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 12, color: C.text }}>
              {session?.name || "Platform Owner"}
            </div>
            <div
              style={{
                fontSize: 10,
                color: C.accent,
                letterSpacing: "0.06em",
              }}
            >
              PLATFORM_OWNER
            </div>
          </div>
          <button
            onClick={handleLogout}
            style={{
              background: "transparent",
              border: `1px solid ${C.border}`,
              color: C.muted,
              fontFamily: FONT_MONO,
              fontSize: 11,
              padding: "5px 12px",
              borderRadius: 5,
              cursor: "pointer",
            }}
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Page header */}
      <div
        style={{
          padding: "28px 28px 0",
          borderBottom: `1px solid ${C.border}`,
          background: C.surface,
        }}
      >
        <div
          style={{
            fontSize: 22,
            fontWeight: 700,
            color: C.text,
            fontFamily: FONT_DISPLAY,
            marginBottom: 4,
          }}
        >
          {tab}
        </div>
        <div style={{ fontSize: 11, color: C.muted, paddingBottom: 20 }}>
          {tab === "Overview" && "Platform health at a glance"}
          {tab === "Stores" && "All registered stores and their subscription status"}
          {tab === "Payments" && "M-PESA subscription payment history across all stores"}
          {tab === "Register Store" && "Onboard a new store and create its admin account"}
        </div>
      </div>

      {/* Content */}
      <div style={{ padding: "24px 28px", maxWidth: 1100 }}>
        {renderTab()}
      </div>
    </div>
  );
}
