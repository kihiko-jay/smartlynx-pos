const isElectron = typeof window !== "undefined" && !!window.electron?.app?.isElectron;

const SS_ACCESS = "dukapos_access";
const SS_REFRESH = "dukapos_refresh";

function readBrowserTokensFromStorage() {
  if (typeof window === "undefined") return { accessToken: null, refreshToken: null };
  try {
    const accessToken = sessionStorage.getItem(SS_ACCESS);
    const refreshToken = sessionStorage.getItem(SS_REFRESH);
    return {
      accessToken: accessToken || null,
      refreshToken: refreshToken || null,
    };
  } catch {
    return { accessToken: null, refreshToken: null };
  }
}

function writeBrowserTokensToStorage(accessToken, refreshToken) {
  try {
    if (accessToken) sessionStorage.setItem(SS_ACCESS, accessToken);
    else sessionStorage.removeItem(SS_ACCESS);
    if (refreshToken) sessionStorage.setItem(SS_REFRESH, refreshToken);
    else sessionStorage.removeItem(SS_REFRESH);
  } catch {
    // ignore storage failures
  }
}

function clearBrowserTokensFromStorage() {
  try {
    sessionStorage.removeItem(SS_ACCESS);
    sessionStorage.removeItem(SS_REFRESH);
  } catch {
    // ignore storage failures
  }
}

async function getApiBase() {
  if (isElectron) {
    const base = await window.electron.config.get("apiBase");
    return base || import.meta.env.VITE_API_URL || "/api/v1";
  }
  return import.meta.env.VITE_API_URL || "/api/v1";
}

async function getTokens() {
  if (isElectron) return window.electron.auth.getTokens();
  return readBrowserTokensFromStorage();
}

async function saveTokens({ accessToken, refreshToken }) {
  if (isElectron) {
    await window.electron.auth.saveTokens({ accessToken, refreshToken });
  } else {
    writeBrowserTokensToStorage(accessToken, refreshToken);
  }

  _tokenCache = {
    accessToken: accessToken || null,
    refreshToken: refreshToken || null,
  };
}

async function clearTokens() {
  if (isElectron) {
    await window.electron.auth.clearTokens();
  } else {
    clearBrowserTokensFromStorage();
  }
}

let _tokenCache = isElectron
  ? { accessToken: null, refreshToken: null }
  : readBrowserTokensFromStorage();

if (isElectron) {
  getTokens().then((tokens) => {
    if (tokens) _tokenCache = { ..._tokenCache, ...tokens };
  });
}

export function getToken() {
  return _tokenCache?.accessToken || null;
}

let _refreshPromise = null;

async function attemptRefresh() {
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    const { refreshToken } = await getTokens();
    if (!refreshToken) throw new Error("No refresh token available");

    const base = await getApiBase();
    const response = await fetch(`${base}/auth/token/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) throw new Error("Refresh failed");

    const data = await response.json();
    await saveTokens({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
    });

    return data.access_token;
  })().finally(() => {
    _refreshPromise = null;
  });

  return _refreshPromise;
}

function normalizeErrorPayload(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .join("; ");
  }
  if (typeof payload.message === "string") return payload.message;
  return fallback;
}

/**
 * Convert network/fetch errors into operator-friendly messages
 */
function translateFetchError(error) {
  if (!error) return "Request failed";
  
  const msg = error.message || "";
  
  // Network-level errors (no response from server)
  if (msg.includes("Failed to fetch") || msg.includes("fetch")) {
    return "Cannot reach the SmartlynX server. Check that the backend is running and the network connection is active.";
  }
  if (msg.includes("ERR_INTERNET_DISCONNECTED")) {
    return "No internet connection. Please check your network.";
  }
  if (msg.includes("ERR_NAME_NOT_RESOLVED") || msg.includes("ENOTFOUND")) {
    return "Server address not found. Check the configured server address.";
  }
  if (msg.includes("ECONNREFUSED")) {
    return "Connection refused. The server may not be running on that address.";
  }
  if (msg.includes("ETIMEDOUT") || msg.includes("timed out")) {
    return "Server took too long to respond. The backend may be down or unreachable.";
  }
  if (msg.includes("ECONNRESET")) {
    return "Connection was reset by the server.";
  }
  
  return msg || "Request failed";
}

async function request(path, options = {}, { retry401 = true } = {}) {
  const base = await getApiBase();
  const accessToken = getToken();
  const headers = {
    ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...(options.headers || {}),
  };

  let response;
  try {
    response = await fetch(`${base}${path}`, {
      ...options,
      credentials: "include",
      headers,
    });
  } catch (fetchErr) {
    // Network-level error (DNS, connection refused, timeout, etc.)
    const friendlyMsg = translateFetchError(fetchErr);
    throw new Error(friendlyMsg);
  }

  if (response.status === 401 && retry401) {
    try {
      const nextAccessToken = await attemptRefresh();
      return request(
        path,
        {
          ...options,
          headers: {
            ...(options.headers || {}),
            Authorization: `Bearer ${nextAccessToken}`,
          },
        },
        { retry401: false }
      );
    } catch {
      await clearSession();
      window.dispatchEvent(new CustomEvent("dukapos:session-expired"));
      try {
        sessionStorage.setItem("smartlynx_session_expired", "1");
      } catch {
        // ignore storage failures
      }
      window.dispatchEvent(
        new CustomEvent("smartlynx:navigate", { detail: { page: "login" } })
      );
      return null;
    }
  }

  if (response.status === 429) {
    const retryAfter = response.headers.get("Retry-After") || "60";
    throw new Error(`Too many requests. Please wait ${retryAfter} seconds.`);
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(normalizeErrorPayload(payload, response.statusText || "Request failed"));
  }

  if (response.status === 204) return null;
  return response.json();
}

async function requestBlob(path, options = {}, { retry401 = true } = {}) {
  const base = await getApiBase();
  const accessToken = getToken();

  const headers = {
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...(options.headers || {}),
  };

  let response;
  try {
    response = await fetch(`${base}${path}`, {
      ...options,
      credentials: "include",
      headers,
    });
  } catch (fetchErr) {
    const friendlyMsg = translateFetchError(fetchErr);
    throw new Error(friendlyMsg);
  }

  if (response.status === 401 && retry401) {
    try {
      const nextAccessToken = await attemptRefresh();
      return requestBlob(
        path,
        {
          ...options,
          headers: {
            ...(options.headers || {}),
            Authorization: `Bearer ${nextAccessToken}`,
          },
        },
        { retry401: false }
      );
    } catch {
      await clearSession();
      window.dispatchEvent(new CustomEvent("dukapos:session-expired"));
      try {
        sessionStorage.setItem("smartlynx_session_expired", "1");
      } catch {
        // ignore storage failures
      }
      window.dispatchEvent(
        new CustomEvent("smartlynx:navigate", { detail: { page: "login" } })
      );
      return null;
    }
  }

  if (response.status === 429) {
    const retryAfter = response.headers.get("Retry-After") || "60";
    throw new Error(`Too many requests. Please wait ${retryAfter} seconds.`);
  }

  if (!response.ok) {
    let payload = null;
    const contentType = response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
      payload = await response.json().catch(() => null);
    } else {
      const text = await response.text().catch(() => "");
      payload = text ? { message: text } : null;
    }

    throw new Error(normalizeErrorPayload(payload, response.statusText || "Request failed"));
  }

  const blob = await response.blob();
  const contentDisposition = response.headers.get("Content-Disposition") || "";
  return {
    blob,
    contentType: response.headers.get("content-type") || "application/octet-stream",
    contentDisposition,
  };
}

const get = (path, params, opts) => {
  const qs = params ? `?${new URLSearchParams(params).toString()}` : "";
  return request(`${path}${qs}`, {}, opts);
};
const post = (path, body, opts) =>
  request(path, { method: "POST", body: JSON.stringify(body ?? {}) }, opts);
const patch = (path, body, opts) =>
  request(path, { method: "PATCH", body: JSON.stringify(body ?? {}) }, opts);
const put = (path, body, opts) =>
  request(path, { method: "PUT", body: JSON.stringify(body ?? {}) }, opts);
const del = (path, opts) => request(path, { method: "DELETE" }, opts);
const getBlob = (path, opts) => requestBlob(path, opts || {}, {});

export const parseMoney = (value) => {
  const num = Number(value ?? 0);
  return isNaN(num) ? 0 : num;
};

export const fmtKES = (value) => {
  const num = parseMoney(value);
  // Display exact value from database - no rounding
  const formatted = num.toLocaleString("en-KE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  return `KES ${formatted}`;
};

export const sessionHelpers = { getTokens, saveTokens, clearTokens };

export function getSession() {
  try {
    const raw = sessionStorage.getItem("dukapos_session");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export async function saveSession(session) {
  try {
    sessionStorage.setItem("dukapos_session", JSON.stringify(session));
  } catch {
    // ignore storage failures
  }

  if (isElectron) {
    try {
      await window.electron.config.set("session", session);
    } catch {
      // ignore electron config failures
    }
  }

  return session;
}

export async function clearSession() {
  await clearTokens();
  _tokenCache = { accessToken: null, refreshToken: null };

  try {
    sessionStorage.removeItem("dukapos_session");
  } catch {
    // ignore storage failures
  }

  if (isElectron) {
    try {
      await window.electron.config.set("session", null);
    } catch {
      // ignore electron config failures
    }
  }
}

export const authAPI = {
  login: (email, password) => post("/auth/login", { email, password }),
  logout: (refreshToken) => post("/auth/logout", refreshToken ? { refresh_token: refreshToken } : {}),
  register: (data) => post("/auth/register", data),
  forgotPassword: ({ email }) => post("/auth/forgot-password", { email }),
  resetPassword: ({ email, token, new_password }) => post("/auth/reset-password", { email, token, new_password }),
  refreshToken: (refreshToken) => post("/auth/token/refresh", refreshToken ? { refresh_token: refreshToken } : {}),
  me: () => get("/auth/me"),
  clockIn: () => post("/auth/clock-in", {}),
  clockOut: () => post("/auth/clock-out", {}),
  wsTicket: () => post("/auth/ws-ticket", {}),
};

export const productsAPI = {
  list: (params) => get("/products", params),
  getById: (id) => get(`/products/${id}`),
  getByBarcode: (barcode) => get(`/products/barcode/${barcode}`),
  getByItemCode: (itemCode) => get(`/products/itemcode/${itemCode}`),
  categories: (params) => get("/products/categories", params),
  createCategory: (data) => post("/products/categories", data),
  suppliers: (params) => get("/products/suppliers", params),
  createSupplier: (data) => post("/products/suppliers", data),
  create: (data) => post("/products", data),
  update: (id, data) => patch(`/products/${id}`, data),
  adjustStock: (data) => post("/products/stock/adjust", data),
  stockHistory: async (id) => {
    const result = await get(`/products/${id}/stock-history`);
    return Array.isArray(result?.movements) ? result.movements : [];
  },
};

export const customersAPI = {
  list: (params) => get("/customers", params),
  getById: (id) => get(`/customers/${id}`),
  create: (data) => post("/customers", data),
  update: (id, data) => patch(`/customers/${id}`, data),
  delete: (id) => fetch(`${import.meta.env.VITE_API_URL || "/api/v1"}/customers/${id}`, { method: "DELETE" }),
  creditSummary: (id) => get(`/customers/${id}/credit-summary`),
  transactionHistory: (id) => get(`/customers/${id}/transactions`),
  bulkActivate: (ids) => post("/customers/bulk/activate", ids),
  bulkDeactivate: (ids) => post("/customers/bulk/deactivate", ids),
  export: (ids) => post("/customers/bulk/export", ids),
  createPayment: (id, data) => post(`/customers/${id}/payments`, data),
  statement: (id, params) => get(`/customers/${id}/statement`, params),
  aging: (params) => get("/customers/aging", params),
};

export const transactionsAPI = {
  create: (data, opts) => post("/transactions", data, opts),
  list: (params) => get("/transactions", params),
  getById: (id) => get(`/transactions/${id}`),
  getByNumber: (txnNumber) =>
    get("/transactions", { search: txnNumber, limit: 1 }).then((r) => {
      const item = Array.isArray(r) ? r[0] : r?.items?.[0];
      if (!item) throw new Error(`Transaction ${txnNumber} not found`);
      return item;
    }),
  todaySummary: () => get("/transactions/summary/today"),
  void: (id) => post(`/transactions/${id}/void`, {}),
};

export const returnsAPI = {
  list: (params) => get("/returns", params),
  getById: (id) => get(`/returns/${id}`),
  create: (data) => post("/returns", data),
  approve: (id, data) => post(`/returns/${id}/approve`, data),
  reject: (id, data) => post(`/returns/${id}/reject`, data),
  listForTransaction: (txnId) => get(`/transactions/${txnId}/returns`),
};

export const mpesaAPI = {
  stkPush: (phone, amount, txnNumber) =>
    post("/mpesa/stk-push", { phone, amount, txn_number: txnNumber }),
  queryStatus: (id) => post("/mpesa/stk-query", { checkout_request_id: id }),
};

export const reportsAPI = {
  zTape: (date) => get("/reports/z-tape", date ? { report_date: date } : {}),
  weekly: (date) => get("/reports/weekly", date ? { week_ending: date } : {}),
  vat: (month, year) => get("/reports/vat", { month, year }),
  topProducts: (date) => get("/reports/top-products", date ? { report_date: date } : {}),
  lowStock: () => get("/reports/low-stock"),
  sales: (params) => get("/reports/z-tape", params),
  inventory: () => get("/reports/low-stock"),
  etims: () => get("/etims/pending"),
};

export const etimsAPI = {
  submit: (id) => post(`/etims/submit/${id}`, {}),
  pending: () => get("/etims/pending"),
  retryAll: () => post("/etims/retry-all", {}),
};

export const auditAPI = {
  trail: (params) => get("/audit/trail", params),
  syncLog: (params) => get("/audit/sync-log", params),
};

export const subscriptionAPI = {
  status: () => get("/subscription/status"),
  register: (data) => post("/subscription/register", data),
  upgrade: (plan, months, mpesaPhone) =>
    post("/subscription/upgrade", { plan, months, mpesa_phone: mpesaPhone }),
};

export const accountingAPI = {
  apAging: (params) => get("/accounting/ap-aging", params),
  arAging: (params) => get("/accounting/ar-aging", params),
  supplierStatement: (supplierId, params) => get(`/accounting/suppliers/${supplierId}/statement`, params),
  customerStatement: (customerId, params) => get(`/accounting/customers/${customerId}/statement`, params),
  consolidatedPL: (params) => get("/accounting/consolidated/pl", params),
  branchComparison: (params) => get("/accounting/branch-comparison", params),
  pl: (params) => get("/accounting/pl", params),
  balanceSheet: (params) => get("/accounting/balance-sheet", params),
  vat: (params) => get("/accounting/vat-summary", params),
  trialBalance: (params) => get("/accounting/trial-balance", params),
  accounts: (params) => get("/accounting/accounts", params),
  journal: (params) => get("/accounting/journal", params),
  ledger: (id, params) => get(`/accounting/ledger/${id}`, params),
  seed: () => post("/accounting/seed", {}),
  createAccount: (data) => post("/accounting/accounts", data),
};

export const expensesAPI = {
  list: (params) => get("/expenses", params),
  create: (data) => post("/expenses", data),
  getById: (id) => get(`/expenses/${id}`),
  void: (id, reason) => request(`/expenses/${id}/void?reason=${encodeURIComponent(reason || "void")}`, { method: "POST" }),
};

export const cashSessionsAPI = {
  list: (params) => get("/cash-sessions", params),
  open: (data) => post("/cash-sessions/open", data),
  close: (id, data) => post(`/cash-sessions/${id}/close`, data),
  getById: (id) => get(`/cash-sessions/${id}`),
};

export const procurementAPI = {
  listPackaging: (productId) => get(`/procurement/products/${productId}/packaging`),
  upsertPackaging: (productId, data) => post(`/procurement/products/${productId}/packaging`, data),
  listPOs: (params) => get("/procurement/purchase-orders", params),
  getPO: (id) => get(`/procurement/purchase-orders/${id}`),
  createPO: (data) => post("/procurement/purchase-orders", data),
  updatePO: (id, data) => patch(`/procurement/purchase-orders/${id}`, data),
  submitPO: (id) => post(`/procurement/purchase-orders/${id}/submit`, {}),
  approvePO: (id) => post(`/procurement/purchase-orders/${id}/approve`, {}),
  cancelPO: (id) => post(`/procurement/purchase-orders/${id}/cancel`, {}),
  listGRNs: (params) => get("/procurement/grns", params),
  getGRN: (id) => get(`/procurement/grns/${id}`),
  createGRN: (data) => post("/procurement/grns", data),
  postGRN: (id) => post(`/procurement/grns/${id}/post`, {}),
  cancelGRN: (id) => post(`/procurement/grns/${id}/cancel`, {}),
  listMatches: (params) => get("/procurement/invoice-matches", params),
  getMatch: (id) => get(`/procurement/invoice-matches/${id}`),
  createMatch: (data) => post("/procurement/invoice-matches", data),
  resolveMatch: (id, data) => patch(`/procurement/invoice-matches/${id}/resolve`, data),
  reportReceived: (params) => get("/procurement/reports/received", params),
  reportOpenPOs: () => get("/procurement/reports/open-pos"),
  downloadPOPdf: (poId, download = true) =>
    getBlob(`/procurement/purchase-orders/${poId}/pdf?download=${download}`),
  sendPOEmail: (poId, { recipient_email, message }) =>
    post(`/procurement/purchase-orders/${poId}/send-email`, {
      recipient_email,
      message,
    }),
  listSupplierPayments: (params) => get("/procurement/supplier-payments", params),
  createSupplierPayment: (data) => post("/procurement/supplier-payments", data),
  getSupplierPayment: (id) => get(`/procurement/supplier-payments/${id}`),
  supplierStatement: (supplierId, params) => get(`/procurement/suppliers/${supplierId}/statement`, params),
  supplierAging: (params) => get("/procurement/suppliers/aging", params),
};

export const platformAPI = {
  metrics: () => get("/platform/metrics"),
  listStores: (params) => get("/platform/stores", params),
  activateStore: (id, plan, months) =>
    request(`/platform/stores/${id}/activate?plan=${encodeURIComponent(plan)}&months=${months}`, {
      method: "POST",
    }),
  suspendStore: (id, reason) =>
    request(`/platform/stores/${id}/suspend?reason=${encodeURIComponent(reason)}`, {
      method: "POST",
    }),
  reinstateStore: (id) => request(`/platform/stores/${id}/reinstate`, { method: "POST" }),
  payments: (params) => get("/platform/payments", params),
  registerStore: (data) => post("/subscription/register", data),
};

export const employeesAPI = {
  listEmployees: () => get("/employees"),
  createEmployee: (data) => post("/employees", data),
  updateEmployee: (id, data) => put(`/employees/${id}`, data),
  deactivateEmployee: (id) => del(`/employees/${id}`),
  resetPassword: (id) => post(`/employees/${id}/reset-password`, {}),
};