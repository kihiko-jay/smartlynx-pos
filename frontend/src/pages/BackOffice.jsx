/**
 * BackOffice — merged finance + staff operations dashboard for Smartlynx.
 */

import { useState, useEffect } from "react";
import { authAPI, clearSession, getSession, sessionHelpers } from "../api/client";
import { useSubscription } from "../hooks/useSubscription";
import UpgradeWall from "../components/UpgradeWall";
import TrialBanner from "../components/TrialBanner";
import ProcurementTab from "./ProcurementTab";
import StaffManagementTab from "./StaffManagementTab";
import AccountingTab from "../components/backoffice/AccountingTab";
import ReturnsTab from "../components/backoffice/ReturnsTab";
import CashSessionsTab from "../components/backoffice/CashSessionsTab";
import ExpensesTab from "../components/backoffice/ExpensesTab";
import { MasterDataTab } from "../components/backoffice/masterData";
import {
  OverviewTab,
  InventoryTab,
  TransactionsTab,
  ReportsTab,
  SyncMonitorTab,
  AuditTrailTab,
  Section,
  shellStyles,
} from "../components/backoffice";

const TABS = [
  "Overview",
  "Inventory",
  "Master Data",
  "Transactions",
  "Returns",
  "Reports",
  "Procurement",
  "Accounting",
  "Cash Sessions",
  "Expenses",
  "Staff Management",
  "Sync Monitor",
  "Audit Trail",
];

export default function BackOffice({ onNavigate }) {
  const [session, setSession] = useState(null);
  const [tab, setTab] = useState("Overview");
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);
  const subscription = useSubscription?.() || {};

  useEffect(() => {
    setSession(getSession());
  }, []);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

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
      await clearSession();
      onNavigate?.("login");
    } catch (err) {
      console.error("Logout error:", err);
      await clearSession();
      onNavigate?.("login");
    }
  };

  const premiumLocked = subscription?.isLoading === false && subscription?.hasAccess === false;

  const renderTab = () => {
    switch (tab) {
      case "Overview": return <OverviewTab />;
      case "Inventory": return <InventoryTab />;
      case "Master Data": return <MasterDataTab />;
      case "Transactions": return <TransactionsTab />;
      case "Returns": return <ReturnsTab />;
      case "Reports": return <ReportsTab />;
      case "Procurement": return <ProcurementTab />;
      case "Accounting": return <AccountingTab />;
      case "Cash Sessions": return <CashSessionsTab />;
      case "Expenses": return <ExpensesTab />;
      case "Staff Management": return <StaffManagementTab />;
      case "Sync Monitor": return <SyncMonitorTab />;
      case "Audit Trail": return <AuditTrailTab />;
      default: return <OverviewTab />;
    }
  };

  return (
    <div style={shellStyles.app}>
      <div style={shellStyles.titleBar(isMobile)}>
        <div style={{ display: "flex", gap: isMobile ? 8 : 18, alignItems: "center", minWidth: isMobile ? "100%" : "auto" }}>
          <div style={{ fontWeight: 800, fontSize: isMobile ? 14 : 20 }}>
            Smartlynx Back Office
          </div>
          {!isMobile && <div style={{ opacity: 0.9, fontSize: 13 }}>Store Control Center</div>}
        </div>
        <div style={{ display: "flex", gap: isMobile ? 6 : 12, alignItems: "center", fontSize: isMobile ? 10 : 12, flexWrap: isMobile ? "wrap" : "nowrap" }}>
          {!isMobile && <span>{session?.name || "Manager"}</span>}
          {!isMobile && <span>{session?.role?.toUpperCase?.() || "ADMIN"}</span>}
          <button style={shellStyles.smallButton(isMobile)} onClick={() => onNavigate?.("pos")}>
            {isMobile ? "POS" : "Go to POS"}
          </button>
          <button style={{ ...shellStyles.smallButton(isMobile), borderColor: "#7a1f1f", color: "#fecaca" }} onClick={handleLogout}>
            {isMobile ? "Out" : "Logout"}
          </button>
        </div>
      </div>

      <div style={{ padding: isMobile ? 12 : 16, display: "grid", gap: isMobile ? 12 : 16 }}>
        <TrialBanner />

        <Section title="Navigation">
          <div style={{ display: "flex", gap: isMobile ? 6 : 10, overflowX: "auto", paddingBottom: 2 }}>
            {TABS.map((t) => (
              <button key={t} onClick={() => setTab(t)} style={shellStyles.tabButton(tab === t, isMobile)}>
                {isMobile ? t.split(" ")[0] : t}
              </button>
            ))}
          </div>
        </Section>

        {premiumLocked ? <UpgradeWall /> : renderTab()}
      </div>
    </div>
  );
}
