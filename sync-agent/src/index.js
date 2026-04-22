/**
 * Smartlynx Sync Agent — Entry Point
 *
 * Runs as a background service (PM2 / Windows Service).
 * Schedules periodic sync cycles for each entity type.
 *
 * Architecture:
 *   - Products, Customers  → every 60s  (timestamp CDC)
 *   - Transactions         → every 10s  (outbox pattern, near-real-time)
 *   - Cloud → Local pulls  → every 5min (price/catalog updates)
 *
 * Safety guarantees:
 *   - Overlapping runs are prevented (lock flag per entity)
 *   - All errors are caught and logged — agent never crashes
 *   - Checkpoints only advance after confirmed cloud write
 */

require("dotenv").config();

const fs = require("fs");

const DEPLOYMENT_MODE = (process.env.DEPLOYMENT_MODE || "single_store").toLowerCase();
const NODE_ROLE = (process.env.NODE_ROLE || "store_server").toLowerCase();
const BRANCH_CODE = (process.env.BRANCH_CODE || "").trim();
const BRANCH_NAME = (process.env.BRANCH_NAME || "").trim();
const STORE_ID = parseInt(process.env.STORE_ID || "0", 10);
if (!STORE_ID || isNaN(STORE_ID)) {
  console.error(
    "[startup] FATAL: STORE_ID environment variable is not set or is not a valid integer.\n" +
    "         Set STORE_ID in sync-agent/.env to the numeric ID of the store this agent serves.\n" +
    "         Example: STORE_ID=1"
  );
  process.exit(1);
}

if (!["single_store", "multi_branch"].includes(DEPLOYMENT_MODE)) {
  console.error(`[startup] FATAL: DEPLOYMENT_MODE must be single_store or multi_branch, got: ${DEPLOYMENT_MODE}`);
  process.exit(1);
}

if (!["store_server", "hq_cloud"].includes(NODE_ROLE)) {
  console.error(`[startup] FATAL: NODE_ROLE must be store_server or hq_cloud, got: ${NODE_ROLE}`);
  process.exit(1);
}

if (DEPLOYMENT_MODE === "multi_branch" && NODE_ROLE === "store_server" && !BRANCH_CODE) {
  console.error("[startup] FATAL: BRANCH_CODE must be set for multi-branch store_server deployments.");
  process.exit(1);
}

const cron   = require("node-cron");
const logger = require("./logger");
const {
  syncProducts,
  syncCustomers,
  syncTransactions,
  pullCloudUpdates,
} = require("./syncLoop");

const { localPool } = require("./db");

// ── Per-entity running locks ──────────────────────────────────────────────────
const running = {
  products:     false,
  customers:    false,
  transactions: false,
  cloudPull:    false,
};

function guard(name, fn) {
  return async () => {
    if (running[name]) {
      logger.debug(`Skipping ${name} sync — previous run still active`);
      return;
    }
    running[name] = true;
    try {
      await fn();
      // Touch the heartbeat file after every successful sync run so Docker's
      // healthcheck can verify the agent loop is still executing.
      // Path is configurable via HEARTBEAT_FILE (default: /app/data/heartbeat).
      if (name === "transactions") {
        const hbFile = process.env.HEARTBEAT_FILE || "/app/data/heartbeat";
        try {
          const now = new Date();
          fs.utimesSync(hbFile, now, now);
        } catch {
          // File may not exist yet on the very first run — create it
          try {
            fs.writeFileSync(process.env.HEARTBEAT_FILE || "/app/data/heartbeat", "");
          } catch (writeErr) {
            logger.warn("Could not write heartbeat file", { error: writeErr.message });
          }
        }
      }
    } catch (err) {
      logger.error(`Unhandled error in ${name} sync`, { error: err.message, stack: err.stack });
    } finally {
      running[name] = false;
    }
  };
}

// ── Scheduler ─────────────────────────────────────────────────────────────────
function startScheduler() {
  const txnInterval  = parseInt(process.env.SYNC_INTERVAL_TRANSACTIONS || "10");
  const prodInterval = parseInt(process.env.SYNC_INTERVAL_PRODUCTS     || "60");
  const custInterval = parseInt(process.env.SYNC_INTERVAL_CUSTOMERS    || "60");

  logger.info("Smartlynx Sync Agent starting", {
    deployment_mode: DEPLOYMENT_MODE,
    node_role: NODE_ROLE,
    branch_code: BRANCH_CODE || null,
    branch_name: BRANCH_NAME || null,
    store_id:      process.env.STORE_ID,
    cloud_api:     process.env.CLOUD_API_URL,
    txn_interval:  `${txnInterval}s`,
    prod_interval: `${prodInterval}s`,
  });

  // Transactions — near real-time
  cron.schedule(`*/${txnInterval} * * * * *`, guard("transactions", syncTransactions));

  // Products
  cron.schedule(`*/${prodInterval} * * * * *`, guard("products", syncProducts));

  // Customers
  cron.schedule(`*/${custInterval} * * * * *`, guard("customers", syncCustomers));

  // Cloud → Local pulls every 5 minutes
  cron.schedule("*/5 * * * *", guard("cloudPull", pullCloudUpdates));

  logger.info("✅ Sync agent running. Press Ctrl+C to stop.");
}

// ── Health check ──────────────────────────────────────────────────────────────
async function healthCheck() {
  try {
    await localPool.query("SELECT 1");
    logger.info("✅ Local DB connection healthy");
  } catch (err) {
    logger.error("❌ Local DB connection failed", { error: err.message });
    process.exit(1);
  }
}

// ── Graceful shutdown ─────────────────────────────────────────────────────────
process.on("SIGINT",  () => { logger.info("Sync agent stopping (SIGINT)");  localPool.end(); process.exit(0); });
process.on("SIGTERM", () => { logger.info("Sync agent stopping (SIGTERM)"); localPool.end(); process.exit(0); });
process.on("uncaughtException",  (err) => logger.error("Uncaught exception",  { error: err.message, stack: err.stack }));
process.on("unhandledRejection", (err) => logger.error("Unhandled rejection", { error: err?.message }));

// ── Start ─────────────────────────────────────────────────────────────────────
healthCheck().then(startScheduler);
