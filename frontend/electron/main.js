/**
 * Smartlynx — Electron Main Process (v4.5.1)
 *
 * OFFLINE QUEUE SAFETY (v4.0):
 *   - Queue is now backed by SQLite (better-sqlite3), NOT electron-store JSON.
 *   - SQLite gives us ACID transactions — a sale is NEVER silently lost.
 *   - Crash during enqueue = transaction rolled back, sale stays in local POS DB.
 *   - Queue survives app restarts, OS crashes, and power cuts.
 *   - Each queued item has a unique idempotency_key to prevent double-posting.
 *
 * AUTH (v4.1):
 *   - Stores both access_token and refresh_token.
 *   - Refresh is attempted transparently before any API call that returns 401.
 *
 * TOKEN SECURITY (v4.1):
 *   Tokens are stored using Electron's safeStorage API (OS keychain / Secret
 *   Service / Keychain Access), NOT in plain electron-store JSON.
 *
 *   safeStorage encrypts with a key derived from the OS user account, so the
 *   ciphertext is unreadable by other OS users or processes. The encrypted
 *   bytes are then stored in a dedicated TokenStore (separate JSON file) so
 *   that a corrupted token file does not affect general app settings.
 *
 *   Fallback: if safeStorage is unavailable (e.g. headless CI), tokens are
 *   held in memory only and cleared on process exit. This is explicitly logged
 *   so operators know tokens will not survive a restart in that environment.
 *
 *   Tokens are NEVER written into the main app settings store.
 */

const { app, BrowserWindow, ipcMain, dialog, shell, Menu, safeStorage } = require("electron");
const path = require("path");
const fs = require("fs");
const isDev = process.env.NODE_ENV === "development";
const Store = require("electron-store");
const Database = require("better-sqlite3");
const { getSetupWizardHTML } = require("./setupWizard");

// ── Persistent config store (settings only — NO tokens here) ─────────────────
const store = new Store({
  defaults: {
    apiBase: "",
    terminalId: "",
    storeName: "",
    storeLocation: "",
    kraPin: "",
    kioskMode: false,
    printerName: "",
    setupMode: "",
    setupWizardCompleted: false,
    // Tokens are stored separately via safeStorage — never here.
  },
});

// ── safeStorage-backed token store ───────────────────────────────────────────
//
// Design:
//   We keep a separate JSON file for token blobs: base64(safeStorage.encryptString(token)).
//   A separate Store prevents token corruption from corrupting app settings.
//
// Memory fallback:
//   If safeStorage is unavailable the tokens are kept in process memory only.
//   They survive for the lifetime of the process but are not persisted to disk.
//   This is acceptable because safeStorage is unavailable only in headless/CI
//   environments where a live POS session would not occur.

let _memTokens = { accessToken: null, refreshToken: null };

// Separate file store for encrypted token blobs
const tokenStore = new Store({ name: "smartlynx-tokens" });

function _safeAvailable() {
  try {
    return safeStorage.isEncryptionAvailable();
  } catch {
    return false;
  }
}

function _readTokens() {
  if (!_safeAvailable()) {
    return { ..._memTokens };
  }
  try {
    const encAccess = tokenStore.get("enc_access", null);
    const encRefresh = tokenStore.get("enc_refresh", null);
    return {
      accessToken: encAccess ? safeStorage.decryptString(Buffer.from(encAccess, "base64")) : null,
      refreshToken: encRefresh ? safeStorage.decryptString(Buffer.from(encRefresh, "base64")) : null,
    };
  } catch (err) {
    console.error("[auth] Token read failed — clearing stored tokens:", err.message);
    tokenStore.clear();
    return { accessToken: null, refreshToken: null };
  }
}

function _writeTokens({ accessToken, refreshToken }) {
  if (!_safeAvailable()) {
    console.warn("[auth] safeStorage unavailable — tokens held in memory only (not persisted)");
    _memTokens = { accessToken, refreshToken };
    return;
  }
  try {
    if (accessToken) {
      tokenStore.set("enc_access", safeStorage.encryptString(accessToken).toString("base64"));
    } else {
      tokenStore.delete("enc_access");
    }
    if (refreshToken) {
      tokenStore.set("enc_refresh", safeStorage.encryptString(refreshToken).toString("base64"));
    } else {
      tokenStore.delete("enc_refresh");
    }
  } catch (err) {
    console.error("[auth] Token write failed:", err.message);
    throw err;
  }
}

function _clearTokens() {
  _memTokens = { accessToken: null, refreshToken: null };
  try {
    tokenStore.clear();
  } catch {
    // ignore
  }
}

// ── SQLite offline queue ──────────────────────────────────────────────────────
let queueDb = null;

function initQueueDb() {
  const userDataPath = app.getPath("userData");
  const dbPath = path.join(userDataPath, "offline_queue.db");

  queueDb = new Database(dbPath);

  // WAL mode: faster writes, crash-safe reads
  queueDb.pragma("journal_mode = WAL");
  queueDb.pragma("synchronous = NORMAL");

  queueDb.exec(`
    CREATE TABLE IF NOT EXISTS offline_queue (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      idempotency_key TEXT    NOT NULL UNIQUE,
      payload         TEXT    NOT NULL,
      queued_at       INTEGER NOT NULL,
      attempts        INTEGER NOT NULL DEFAULT 0,
      last_error      TEXT,
      status          TEXT    NOT NULL DEFAULT 'pending'
    );
    CREATE INDEX IF NOT EXISTS idx_oq_status ON offline_queue(status);
  `);

  console.log("[offline-queue] SQLite queue initialised at", dbPath);
}

// ── Window reference ───────────────────────────────────────────────────────────
let mainWindow = null;
let setupWindow = null;

function createWindow() {
  const kioskMode = store.get("kioskMode");

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 600,
    fullscreen: kioskMode,
    kiosk: kioskMode,
    frame: !kioskMode,
    titleBarStyle: "hidden",
    backgroundColor: "#0a0c0f",
    icon: path.join(__dirname, "../assets/icon.png"),
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
    },
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:3000");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  mainWindow.webContents.on("will-navigate", (event, url) => {
    const appUrl = isDev ? "http://localhost:3000" : `file://${path.join(__dirname, "../dist")}`;
    if (!url.startsWith(appUrl)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  // Inject Content-Security-Policy meta tag into the renderer
  mainWindow.webContents.on("did-finish-load", () => {
    const csp = [
      "default-src 'self'",
      "script-src 'self'",
      "style-src 'self' 'unsafe-inline'",
      "connect-src 'self' http: https: ws: wss:",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; ");

    mainWindow.webContents
      .executeJavaScript(`
        (function() {
          const existing = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
          if (existing) return;
          const meta = document.createElement('meta');
          meta.setAttribute('http-equiv', 'Content-Security-Policy');
          meta.setAttribute('content', ${JSON.stringify(csp)});
          document.head.prepend(meta);
        })();
      `)
      .catch(() => {});
  });
}

/**
 * Open setup wizard as a standalone window (not modal to hidden parent).
 * This ensures visibility and proper focus on all platforms.
 */
function createStandaloneSetupWindow() {
  if (setupWindow) {
    setupWindow.focus();
    return;
  }

  setupWindow = new BrowserWindow({
    width: 700,
    height: 850,
    title: "SmartlynX Setup Wizard",
    backgroundColor: "#f6f8fb",
    show: true, // Show immediately so it's not hidden
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  setupWindow.loadURL(
    `data:text/html;charset=utf-8,${encodeURIComponent(getSetupWizardHTML(null))}`
  );

  setupWindow.on("closed", () => {
    setupWindow = null;
  });
}

// ── App lifecycle ──────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  initQueueDb();
  if (!isDev) Menu.setApplicationMenu(null);

  const shouldShowWizard = (() => {
    const apiBase = store.get("apiBase", "").trim();
    const terminalId = store.get("terminalId", "").trim();
    return !apiBase || !terminalId;
  })();

  if (shouldShowWizard) {
    // First run: show setup wizard as standalone window, main window stays hidden initially
    createStandaloneSetupWindow();
    // Still create main window in background for immediate readiness after setup
    createWindow();
  } else {
    // Normal run: create and show main window immediately
    createWindow();
    mainWindow.show();
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
      mainWindow.show();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    if (queueDb) queueDb.close();
    app.quit();
  }
});

// ── IPC: Config ────────────────────────────────────────────────────────────────
ipcMain.handle("config:get", (_, key) => store.get(key));

const WRITABLE_CONFIG_KEYS = new Set([
  "apiBase",
  "terminalId",
  "storeName",
  "storeLocation",
  "kraPin",
  "kioskMode",
  "printerName",
  "setupMode",
  "setupWizardCompleted",
]);

ipcMain.handle("config:set", (_, key, value) => {
  if (!WRITABLE_CONFIG_KEYS.has(key)) {
    console.warn(`[ipc:config:set] Blocked write to non-allowlisted key: ${key}`);
    return false;
  }
  store.set(key, value);
  return true;
});

ipcMain.handle("config:getAll", () => store.store);

// ── IPC: App info ──────────────────────────────────────────────────────────────
ipcMain.handle("app:getVersion", () => app.getVersion());

const ALLOWED_APP_PATHS = new Set(["userData", "temp", "logs", "downloads"]);
ipcMain.handle("app:getPath", (_, name) => {
  if (!ALLOWED_APP_PATHS.has(name)) {
    console.warn(`[ipc:app:getPath] Blocked request for path: ${name}`);
    return null;
  }
  return app.getPath(name);
});

// ── IPC: Window controls ───────────────────────────────────────────────────────
ipcMain.handle("window:minimize", () => mainWindow?.minimize());
ipcMain.handle("window:maximize", () =>
  mainWindow?.isMaximized() ? mainWindow.restore() : mainWindow.maximize()
);
ipcMain.handle("window:close", () => mainWindow?.close());
ipcMain.handle("window:fullscreen", () => mainWindow?.setFullScreen(!mainWindow.isFullScreen()));
ipcMain.handle("window:reload", () => mainWindow?.reload());

// ── IPC: Token management — safeStorage backed (v4.1) ────────────────────────
ipcMain.handle("auth:saveTokens", (_, { accessToken, refreshToken }) => {
  _writeTokens({ accessToken, refreshToken });
  return true;
});

ipcMain.handle("auth:getTokens", () => _readTokens());

ipcMain.handle("auth:clearTokens", () => {
  _clearTokens();
  return true;
});

// ── IPC: Offline queue (SQLite-backed) ────────────────────────────────────────
ipcMain.handle("offline:enqueue", (_, transaction) => {
  if (!queueDb) return { success: false, error: "Queue DB not ready" };

  const key =
    transaction.idempotency_key ||
    transaction.txn_number ||
    `offline-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  try {
    const stmt = queueDb.prepare(`
      INSERT OR IGNORE INTO offline_queue (idempotency_key, payload, queued_at, status)
      VALUES (?, ?, ?, 'pending')
    `);
    const info = stmt.run(key, JSON.stringify({ ...transaction, idempotency_key: key }), Date.now());

    const count = queueDb
      .prepare("SELECT COUNT(*) as n FROM offline_queue WHERE status = 'pending'")
      .get();

    console.log(`[offline-queue] Enqueued ${key} (queue depth: ${count.n})`);
    return { success: true, idempotency_key: key, queueLength: count.n };
  } catch (err) {
    console.error("[offline-queue] Enqueue failed:", err.message);
    return { success: false, error: err.message };
  }
});

ipcMain.handle("offline:getQueue", () => {
  if (!queueDb) return [];
  const rows = queueDb
    .prepare(`
      SELECT * FROM offline_queue
      WHERE status IN ('pending', 'failed')
      ORDER BY queued_at ASC
    `)
    .all();
  return rows.map((r) => JSON.parse(r.payload));
});

ipcMain.handle("offline:clearItem", (_, idempotency_key) => {
  if (!queueDb) return { remaining: 0 };
  queueDb
    .prepare(`
      UPDATE offline_queue SET status = 'synced' WHERE idempotency_key = ?
    `)
    .run(idempotency_key);

  const count = queueDb
    .prepare("SELECT COUNT(*) as n FROM offline_queue WHERE status = 'pending'")
    .get();

  return { remaining: count.n };
});

ipcMain.handle("offline:markFailed", (_, idempotency_key, error) => {
  if (!queueDb) return;
  queueDb
    .prepare(`
      UPDATE offline_queue
      SET attempts = attempts + 1, last_error = ?, status = 'failed'
      WHERE idempotency_key = ?
    `)
    .run(String(error), idempotency_key);
});

ipcMain.handle("offline:stats", () => {
  if (!queueDb) return { pending: 0, failed: 0, synced: 0 };
  const row = queueDb
    .prepare(`
      SELECT
        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
        SUM(CASE WHEN status = 'failed'  THEN 1 ELSE 0 END) as failed,
        SUM(CASE WHEN status = 'synced'  THEN 1 ELSE 0 END) as synced
      FROM offline_queue
    `)
    .get();
  return row;
});

ipcMain.handle("offline:clearAll", () => {
  if (!queueDb) return true;
  queueDb
    .prepare("UPDATE offline_queue SET status = 'synced' WHERE status IN ('pending','failed')")
    .run();
  return true;
});

// ── IPC: Cash drawer ───────────────────────────────────────────────────────────
ipcMain.handle("drawer:open", async () => {
  try {
    const printerName = store.get("printerName");
    if (!printerName) {
      return { success: false, error: "No printer configured for cash drawer" };
    }

    return {
      success: false,
      error: `Cash drawer transport not yet implemented for printer ${printerName}`,
      code: "DRAWER_NOT_IMPLEMENTED",
    };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

// ── IPC: Receipt printing ──────────────────────────────────────────────────────
ipcMain.handle("printer:printReceipt", async (_, receiptData) => {
  try {
    const printerName = store.get("printerName");
    const lines = buildReceiptText(receiptData);
    const { exec } = require("child_process");
    const tmpFile = path.join(app.getPath("temp"), "receipt.txt");

    fs.writeFileSync(tmpFile, lines.join("\n"));

    if (process.platform === "win32") {
      exec(`notepad /p "${tmpFile}"`);
    } else {
      exec(`lp -d "${printerName}" "${tmpFile}"`);
    }

    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle("printer:getList", async () => {
  try {
    const printers = await mainWindow.webContents.getPrintersAsync();
    return printers.map((p) => ({ name: p.name, isDefault: p.isDefault, status: p.status }));
  } catch {
    return [];
  }
});

// ── IPC: Dialogs ───────────────────────────────────────────────────────────────
ipcMain.handle("dialog:confirm", async (_, { title, message }) => {
  const result = await dialog.showMessageBox(mainWindow, {
    type: "question",
    buttons: ["Cancel", "Confirm"],
    title,
    message,
  });
  return result.response === 1;
});

ipcMain.handle("dialog:error", async (_, { title, message }) => {
  await dialog.showErrorBox(title, message);
});

// ── IPC: UI Recovery — reopen setup/settings from login ─────────────────────────
ipcMain.handle("ui:reopenSetup", async () => {
  try {
    createStandaloneSetupWindow();
    return { success: true };
  } catch (error) {
    console.error("[ui:reopenSetup]", error.message);
    return { success: false, error: error.message };
  }
});

ipcMain.handle("ui:openSettings", async () => {
  try {
    const { openSettings } = require("./settings");
    if (mainWindow) {
      openSettings(mainWindow, store);
    }
    return { success: true };
  } catch (error) {
    console.error("[ui:openSettings]", error.message);
    return { success: false, error: error.message };
  }
});

// ── IPC: Setup Wizard ──────────────────────────────────────────────────────────
ipcMain.handle("setup:shouldShow", () => {
  const apiBase = store.get("apiBase", "").trim();
  const terminalId = store.get("terminalId", "").trim();
  return !apiBase || !terminalId;
});

ipcMain.handle("setup:testConnection", async (_, { apiBase }) => {
  if (!apiBase) {
    return { success: false, error: "Server address is required" };
  }

  try {
    try {
      new URL(apiBase);
    } catch {
      return { success: false, error: "Invalid URL format" };
    }

    const normalizedBase = apiBase.replace(/\/+$/, "");
    const apiRoot = normalizedBase.replace(/\/api\/v1\/?$/, "");
    const readyUrl = `${apiRoot}/ready`;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(readyUrl, {
        method: "GET",
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (response.ok) {
        return { success: true, statusCode: response.status };
      } else if (response.status >= 500) {
        return {
          success: false,
          error: `Server error (HTTP ${response.status}). Backend may not be healthy.`,
          statusCode: response.status,
        };
      } else {
        return { success: true, statusCode: response.status };
      }
    } catch (fetchErr) {
      clearTimeout(timeout);

      if (fetchErr.name === "AbortError") {
        return { success: false, error: "Server did not respond within 5 seconds" };
      }
      throw fetchErr;
    }
  } catch (error) {
    console.error("[setup:testConnection]", error.message);

    if (error.code === "ECONNREFUSED") {
      return { success: false, error: "Cannot reach server. Check address and network." };
    } else if (error.code === "ENOTFOUND") {
      return { success: false, error: "Server address not found. Check the URL." };
    } else {
      return { success: false, error: `Network error: ${error.message}` };
    }
  }
});

ipcMain.handle("setup:testLogin", async (_, { apiBase, email, password }) => {
  if (!apiBase || !email || !password) {
    return { success: false, error: "Server, email, and password are required" };
  }

  try {
    const normalizedBase = apiBase.replace(/\/+$/, "");
    const loginUrl = `${normalizedBase}/auth/login`;

    const response = await fetch(loginUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const errorMsg = data.message || data.detail || "Invalid credentials or server error";
      return { success: false, error: errorMsg };
    }

    const data = await response.json();
    return {
      success: true,
      userName: data.full_name || data.name || "User",
    };
  } catch (error) {
    console.error("[setup:testLogin]", error.message);
    return { success: false, error: `Connection error: ${error.message}` };
  }
});

ipcMain.handle("setup:getPrinterList", async () => {
  if (!mainWindow) return [];
  try {
    const printers = await mainWindow.webContents.getPrintersAsync();
    return printers.map((p) => ({ name: p.name, isDefault: p.isDefault, status: p.status }));
  } catch (error) {
    console.error("[setup:getPrinterList]", error.message);
    return [];
  }
});

ipcMain.handle("setup:testPrintReceipt", async (_, { printerName }) => {
  if (!printerName) {
    return { success: false, error: "No printer selected" };
  }

  try {
    const testReceipt = {
      storeName: store.get("storeName", "TEST STORE"),
      txnNumber: "TEST-001",
      items: [{ product_name: "Test Item", qty: 1, line_total: 100 }],
      subtotal: 100,
      vatAmount: 16,
      total: 116,
      paymentMethod: "CASH",
      cashTendered: 200,
      changeGiven: 84,
      time: new Date().toLocaleString("en-KE"),
    };

    const lines = buildReceiptText(testReceipt);
    const { exec } = require("child_process");
    const tmpFile = path.join(app.getPath("temp"), "receipt-test.txt");

    fs.writeFileSync(tmpFile, lines.join("\n"));

    if (process.platform === "win32") {
      exec(`notepad /p "${tmpFile}"`);
    } else {
      exec(`lp -d "${printerName}" "${tmpFile}"`);
    }

    return { success: true };
  } catch (error) {
    console.error("[setup:testPrintReceipt]", error.message);
    return { success: false, error: error.message };
  }
});

ipcMain.handle("setup:saveConfig", (_, configObj) => {
  try {
    if (!configObj || typeof configObj !== "object") {
      return { success: false, error: "Invalid config object" };
    }

    for (const [key, value] of Object.entries(configObj)) {
      if (!WRITABLE_CONFIG_KEYS.has(key)) {
        console.warn(`[setup:saveConfig] Skipping non-allowlisted key: ${key}`);
        continue;
      }
      store.set(key, value);
    }

    return { success: true };
  } catch (error) {
    console.error("[setup:saveConfig]", error.message);
    return { success: false, error: error.message };
  }
});

ipcMain.handle("setup:markCompleted", () => {
  try {
    store.set("setupWizardCompleted", true);
    
    // Show main window after setup completes
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
    
    // Close setup wizard window
    if (setupWindow) {
      setupWindow.close();
    }
    
    return { success: true };
  } catch (error) {
    console.error("[setup:markCompleted]", error.message);
    return { success: false, error: error.message };
  }
});

// ── Receipt builder ────────────────────────────────────────────────────────────
function buildReceiptText(data) {
  const {
    storeName,
    txnNumber,
    items,
    subtotal,
    vatAmount,
    total,
    paymentMethod,
    cashTendered,
    changeGiven,
    mpesaRef,
    etimsInvoice,
    time,
  } = data;

  const w = 40;
  const sep = "─".repeat(w);
  const center = (s) => s.padStart(Math.floor((w + s.length) / 2)).padEnd(w);
  const lr = (l, r) => l + r.padStart(w - l.length);

  const kraPin = store.get("kraPin", "");
  const storeLocation = store.get("storeLocation", "Nairobi, Kenya");

  return [
    center(storeName || "SMARTLYNX STORE"),
    center(storeLocation),
    ...(kraPin ? [center(`PIN: ${kraPin}`)] : []),
    sep,
    `TXN: ${txnNumber}`,
    `Date: ${time || new Date().toLocaleString("en-KE")}`,
    sep,
    ...(items || []).map((i) => lr(`${i.product_name} x${i.qty}`, `KES ${i.line_total.toFixed(2)}`)),
    sep,
    lr("Subtotal:", `KES ${(subtotal || 0).toFixed(2)}`),
    lr("VAT (16%):", `KES ${(vatAmount || 0).toFixed(2)}`),
    lr("TOTAL:", `KES ${(total || 0).toFixed(2)}`),
    sep,
    lr("Payment:", (paymentMethod || "").toUpperCase()),
    ...(cashTendered
      ? [
          lr("Cash:", `KES ${cashTendered.toFixed(2)}`),
          lr("Change:", `KES ${(changeGiven || 0).toFixed(2)}`),
        ]
      : []),
    ...(mpesaRef ? [`M-PESA Ref: ${mpesaRef}`] : []),
    sep,
    `eTIMS: ${etimsInvoice || "PENDING"}`,
    center("Thank you for shopping with us!"),
    center("Powered by Smartlynx"),
    "",
    "",
  ];
}