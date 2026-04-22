import { useState, useEffect } from "react";
import { getSession, clearSession, cashSessionsAPI } from "../../api/client";

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

    cashSessionsAPI
      .list()
      .then((rows) => {
        const open = (rows || []).find(
          (r) =>
            r.status === "open" &&
            String(r.cashier_id) === String(session.id) &&
            String(r.terminal_id || "") === String(session.terminal_id || "")
        );

        setCurrentCashSession(open || null);
      })
      .catch(() => {
        setCurrentCashSession(null);
      })
      .finally(() => {
        setCashSessionsLoaded(true);
      });
  }, [session]);

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
      setCurrentCashSession(newSession);
      return newSession;
    } catch (err) {
      throw new Error(err.message || "Failed to open cash session");
    }
  };

  const closeCashSession = async (countedCash, notes = "") => {
    if (!currentCashSession?.id) {
      throw new Error("No open cash session");
    }
    try {
      const closed = await cashSessionsAPI.close(currentCashSession.id, {
        counted_cash: parseFloat(countedCash) || 0,
        notes: notes.trim(),
      });
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