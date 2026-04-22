# Smartlynx Sync Agent — Dockerfile

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN apk add --no-cache python3 make g++ && \
    npm ci --omit=dev && \
    apk del python3 make g++

FROM node:20-alpine AS runtime
LABEL org.opencontainers.image.title="Smartlynx Sync Agent"
LABEL org.opencontainers.image.description="Local to cloud data synchronisation agent"
LABEL org.opencontainers.image.version="4.5.1"

WORKDIR /app
RUN addgroup -S syncagent && adduser -S syncagent -G syncagent
COPY --from=deps /app/node_modules ./node_modules
COPY src/ ./src/
COPY package.json .
VOLUME ["/app/data", "/app/logs"]
ENV NODE_ENV=production \
    LOG_LEVEL=info \
    RETRY_QUEUE_PATH=/app/data/retry_queue.db \
    SYNC_INTERVAL_TRANSACTIONS=10 \
    SYNC_INTERVAL_PRODUCTS=60 \
    SYNC_INTERVAL_CUSTOMERS=60 \
    BATCH_SIZE=500
RUN mkdir -p /app/data /app/logs && chown -R syncagent:syncagent /app
USER syncagent
HEALTHCHECK --interval=60s --timeout=10s --start-period=15s --retries=3 \
  CMD node -e "require('fs').accessSync('/app/src/index.js'); process.exit(0);" 2>/dev/null || exit 1
CMD ["node", "src/index.js"]
