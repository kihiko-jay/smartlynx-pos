import { useEffect, useMemo, useState } from "react";
import { clearSession, getSession } from "./api/client";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import POSTerminal from "./pages/POSTerminal";
import BackOffice from "./pages/BackOffice";
import PlatformDashboard from "./pages/PlatformDashboard";
import ErrorBoundary from "./components/ErrorBoundary";

function getInitialPage() {
  const session = getSession();
  const url = new URL(window.location.href);
  const hasResetToken = !!url.searchParams.get("token");

  if (hasResetToken || url.pathname.endsWith("/reset-password") || window.location.hash.startsWith("#/reset-password")) {
    return "reset-password";
  }

  if (session) return routeForRole(session.role);
  return "login";
}

export default function App() {
  const [page, setPage] = useState(() => getInitialPage());
  const [bootError, setBootError] = useState("");
  const session = useMemo(() => getSession(), [page]);

  useEffect(() => {
    const handleNavigate = (event) => {
      const nextPage = event?.detail?.page;
      if (nextPage) setPage(nextPage);
    };

    const handleSessionExpired = async () => {
      await clearSession();
      setBootError("Your session expired. Please sign in again.");
      setPage("login");
    };

    const handleHashChange = () => {
      if (window.location.hash.startsWith("#/reset-password")) {
        setPage("reset-password");
      }
    };

    window.addEventListener("smartlynx:navigate", handleNavigate);
    window.addEventListener("dukapos:session-expired", handleSessionExpired);
    window.addEventListener("hashchange", handleHashChange);

    try {
      const expiredFlag = sessionStorage.getItem("smartlynx_session_expired");
      if (expiredFlag) {
        sessionStorage.removeItem("smartlynx_session_expired");
        setBootError("Your session expired. Please sign in again.");
        setPage("login");
      }
    } catch {
      // ignore storage failures
    }

    return () => {
      window.removeEventListener("smartlynx:navigate", handleNavigate);
      window.removeEventListener("dukapos:session-expired", handleSessionExpired);
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, []);

  const handleLogin = (data) => {
    setBootError("");
    setPage(routeForRole(data.role));
  };

  const handleLogout = async () => {
    await clearSession();
    setPage("login");
  };

  const sharedAuthProps = {
    session,
    bootError,
    onClearBootError: () => setBootError(""),
  };

  if (page === "login") {
    return (
      <ErrorBoundary fallbackLabel="Login">
        <Login onLogin={handleLogin} onNavigate={setPage} {...sharedAuthProps} />
      </ErrorBoundary>
    );
  }

  if (page === "register") {
    return (
      <ErrorBoundary fallbackLabel="Register">
        <Register onNavigate={setPage} />
      </ErrorBoundary>
    );
  }

  if (page === "forgot-password") {
    return (
      <ErrorBoundary fallbackLabel="Forgot Password">
        <ForgotPassword onNavigate={setPage} />
      </ErrorBoundary>
    );
  }

  if (page === "reset-password") {
    return (
      <ErrorBoundary fallbackLabel="Reset Password">
        <ResetPassword onNavigate={setPage} />
      </ErrorBoundary>
    );
  }

  if (page === "platform") {
    return (
      <ErrorBoundary fallbackLabel="Platform Dashboard">
        <PlatformDashboard onLogout={handleLogout} />
      </ErrorBoundary>
    );
  }

  if (page === "backoffice") {
    return (
      <ErrorBoundary fallbackLabel="Back Office">
        <BackOffice onNavigate={setPage} />
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary fallbackLabel="POS Terminal">
      <POSTerminal onNavigate={setPage} />
    </ErrorBoundary>
  );
}

function routeForRole(role) {
  if (role === "platform_owner") return "platform";
  if (["manager", "admin"].includes(role)) return "backoffice";
  return "pos";
}
