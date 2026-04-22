/**
 * useSubscription — fetches and caches the store's plan status.
 * Used everywhere a premium gate is needed.
 */
import { useState, useEffect } from "react";
import { getToken } from "../api/client";

const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

async function fetchStatus() {
  const token = getToken();
  if (!token) return null;
  const res  = await fetch(`${API_BASE}/subscription/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json();
}

export function useSubscription() {
  const [status,  setStatus]  = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setLoading(false));
  }, []);

  return {
    loading,
    isPremium:  status?.is_premium  ?? false,
    plan:       status?.plan        ?? "free",
    planLabel:  status?.plan_label  ?? "Free",
    status:     status?.status      ?? "free",
    daysLeft:   status?.days_left   ?? 0,
    isTrialing: status?.status      === "trialing",
    plans:      status?.available_plans ?? [],
    storeName:  status?.store_name  ?? "",
    raw:        status,
  };
}
