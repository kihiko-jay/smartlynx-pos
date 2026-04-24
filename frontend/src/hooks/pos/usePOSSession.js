import { useState, useEffect } from "react";
import { cashSessionsAPI } from "../../api/client";

const isElectron =
  typeof window !== "undefined" && !!window.electron?.app?.isElectron;

async function readSession() {
  if (typeof window !== "undefined" && window.electron?.config) {
    return window.electron.config.get("session");
  }
  try {
    return JSON.parse(sessionStorage.getItem("dukapos_session"));
  } catch {
    return null;
  }
}

async function saveSessionToElectron(session) {
  if (isElectron && window.electron?.config) {
    await window.electron.config.set("session", session);
  }
}

export function usePOSSession() {
  const [session, setSession] = useState(null);
  const [showSecureLogin, setShowSecureLogin] = useState(false);
  const [secureEmail, setSecureEmail] = useState("");
  const [securePassword, setSecurePassword] = useState("");
  const [secureLoading, setSecureLoading] = useState(false);
  const [secureError, setSecureError] = useState("");
  const [currentCashSession, setCurrentCashSession] = useState(null);
  const [cashSessionsLoaded, setCashSessionsLoaded] = useState(false);

  useEffect(() => {
    readSession().then(setSession);
  }, []);

  useEffect(() => {
    if (!session) return;

    setCashSessionsLoaded(false);
    
    // Use a unique cache key based on cashier ID to prevent stale data
    const fetchCurrentSession = async () => {
      try {
        const row = await cashSessionsAPI.current();
        console.log("Fetched current cash session:", row);
        setCurrentCashSession(row || null);
      } catch (err) {
        console.error("Failed to fetch cash session:", err);
        setCurrentCashSession(null);
      } finally {
        setCashSessionsLoaded(true);
      }
    };
    
    fetchCurrentSession();
  }, [session?.id]); // Re-fetch when cashier ID changes

  const openSecureLogin = () => {
    setSecureEmail("");
    setSecurePassword("");
    setSecureError("");
    setShowSecureLogin(true);
  };

  const closeSecureLogin = () => {
    setShowSecureLogin(false);
    setSecureEmail("");
    setSecurePassword("");
    setSecureError("");
  };

  const openCashSession = async (terminalId, openingFloat, notes = "") => {
    try {
      const newSession = await cashSessionsAPI.open({
        terminal_id: terminalId,
        opening_float: parseFloat(openingFloat) || 0,
        notes: notes.trim(),
      });
      console.log("Cash session opened:", newSession);
      setCurrentCashSession(newSession);
      return newSession;
    } catch (err) {
      throw new Error(err.message || "Failed to open cash session");
    }
  };

  const closeCashSession = async (paymentData) => {
    if (!currentCashSession?.id) {
      throw new Error("No open cash session");
    }
    try {
      const closed = await cashSessionsAPI.close(currentCashSession.id, paymentData);
      console.log("Cash session closed:", closed);
      setCurrentCashSession(null);
      return closed;
    } catch (err) {
      throw new Error(err.message || "Failed to close cash session");
    }
  };

  return {
    session,
    setSession,
    showSecureLogin,
    setShowSecureLogin,
    secureEmail,
    setSecureEmail,
    securePassword,
    setSecurePassword,
    secureLoading,
    setSecureLoading,
    secureError,
    setSecureError,
    openSecureLogin,
    closeSecureLogin,
    saveSessionToElectron,
    currentCashSession,
    setCurrentCashSession,
    cashSessionsLoaded,
    openCashSession,
    closeCashSession,
  };
}