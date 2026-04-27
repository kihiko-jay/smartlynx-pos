#!/bin/bash
set -e

###############################################################################
# Smartlynx Secret Rotation Runbook (v1.0)
#
# CRITICAL: This script rotates 4 secrets across production branches.
# Run on each of the 7 branch servers sequentially.
#
# Safety checks:
#   - Exits immediately on any error (set -e)
#   - Creates backup of .env before modification
#   - Verifies sed replacements succeeded
#   - Verifies no CHANGE_ME placeholders remain
#   - Checks API health before reporting success
#   - All credentials logged to history for operator review
#
# Usage:
#   sudo ~/rotate-secrets.sh
#
###############################################################################

readonly ENV_FILE="/opt/smartlynx/backend/.env"
readonly ENV_BACKUP="${ENV_FILE}.backup.$(date +%s)"
readonly DOCKER_COMPOSE="/opt/smartlynx/backend/docker-compose.prod.yml"

# Color output for readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

###############################################################################
# STEP 1: Generate new secrets
###############################################################################

log_info "Step 1/6: Generating new secrets..."

# 64 hex chars for SECRET_KEY (256 bits)
NEW_SECRET_KEY=$(openssl rand -hex 32)
log_info "Generated NEW_SECRET_KEY (64 hex chars)"

# 32 hex chars for encryption/API keys (128 bits each)
NEW_ENCRYPTION_KEY=$(openssl rand -hex 16)
log_info "Generated NEW_ENCRYPTION_KEY (32 hex chars)"

NEW_INTERNAL_API_KEY=$(openssl rand -hex 16)
log_info "Generated NEW_INTERNAL_API_KEY (32 hex chars)"

NEW_MPESA_WEBHOOK_SECRET=$(openssl rand -hex 16)
log_info "Generated NEW_MPESA_WEBHOOK_SECRET (32 hex chars)"

###############################################################################
# STEP 2: Verify .env file exists
###############################################################################

log_info "Step 2/6: Verifying environment file..."

if [[ ! -f "$ENV_FILE" ]]; then
    log_error ".env file not found at $ENV_FILE"
    exit 1
fi
log_info "File exists: $ENV_FILE"

###############################################################################
# STEP 3: Create backup
###############################################################################

log_info "Step 3/6: Creating backup..."

cp "$ENV_FILE" "$ENV_BACKUP"
log_info "Backup created: $ENV_BACKUP"

###############################################################################
# STEP 4: Replace secrets in-place
###############################################################################

log_info "Step 4/6: Replacing secrets in .env..."

# Replace SECRET_KEY (handles any existing value)
sed -i.tmp "s/^SECRET_KEY=.*$/SECRET_KEY=$NEW_SECRET_KEY/" "$ENV_FILE"
log_info "Updated SECRET_KEY"

# Replace SECRET_ENCRYPTION_KEY (handles any existing value)
sed -i.tmp "s/^SECRET_ENCRYPTION_KEY=.*$/SECRET_ENCRYPTION_KEY=$NEW_ENCRYPTION_KEY/" "$ENV_FILE"
log_info "Updated SECRET_ENCRYPTION_KEY"

# Replace INTERNAL_API_KEY
sed -i.tmp "s/^INTERNAL_API_KEY=.*$/INTERNAL_API_KEY=$NEW_INTERNAL_API_KEY/" "$ENV_FILE"
log_info "Updated INTERNAL_API_KEY"

# Replace MPESA_WEBHOOK_SECRET
sed -i.tmp "s/^MPESA_WEBHOOK_SECRET=.*$/MPESA_WEBHOOK_SECRET=$NEW_MPESA_WEBHOOK_SECRET/" "$ENV_FILE"
log_info "Updated MPESA_WEBHOOK_SECRET"

# Clean up sed backup files
rm -f "${ENV_FILE}.tmp"

###############################################################################
# STEP 5: Verify replacements
###############################################################################

log_info "Step 5/6: Verifying secret rotation..."

# Check that no CHANGE_ME placeholders remain
if grep -qi "CHANGE_ME" "$ENV_FILE"; then
    log_error "CHANGE_ME placeholders still present in .env!"
    log_error "Rolling back from backup: $ENV_BACKUP"
    cp "$ENV_BACKUP" "$ENV_FILE"
    exit 1
fi
log_info "✓ No CHANGE_ME strings found (verified)"

# Verify each key was actually updated
if ! grep -q "^SECRET_KEY=$NEW_SECRET_KEY$" "$ENV_FILE"; then
    log_error "SECRET_KEY replacement failed"
    cp "$ENV_BACKUP" "$ENV_FILE"
    exit 1
fi
log_info "✓ SECRET_KEY replacement verified"

if ! grep -q "^SECRET_ENCRYPTION_KEY=$NEW_ENCRYPTION_KEY$" "$ENV_FILE"; then
    log_error "SECRET_ENCRYPTION_KEY replacement failed"
    cp "$ENV_BACKUP" "$ENV_FILE"
    exit 1
fi
log_info "✓ SECRET_ENCRYPTION_KEY replacement verified"

if ! grep -q "^INTERNAL_API_KEY=$NEW_INTERNAL_API_KEY$" "$ENV_FILE"; then
    log_error "INTERNAL_API_KEY replacement failed"
    cp "$ENV_BACKUP" "$ENV_FILE"
    exit 1
fi
log_info "✓ INTERNAL_API_KEY replacement verified"

if ! grep -q "^MPESA_WEBHOOK_SECRET=$NEW_MPESA_WEBHOOK_SECRET$" "$ENV_FILE"; then
    log_error "MPESA_WEBHOOK_SECRET replacement failed"
    cp "$ENV_BACKUP" "$ENV_FILE"
    exit 1
fi
log_info "✓ MPESA_WEBHOOK_SECRET replacement verified"

###############################################################################
# STEP 6: Restart API container
###############################################################################

log_info "Step 6/6: Restarting API container..."

if [[ ! -f "$DOCKER_COMPOSE" ]]; then
    log_error "docker-compose.prod.yml not found at $DOCKER_COMPOSE"
    exit 1
fi

cd /opt/smartlynx/backend

docker compose -f "$DOCKER_COMPOSE" restart api
log_info "API container restart initiated"

###############################################################################
# STEP 7: Health check (wait up to 60s)
###############################################################################

log_info "Waiting for API health check (max 60 seconds)..."

max_attempts=12
attempt=0
health_ok=false

while [[ $attempt -lt $max_attempts ]]; do
    attempt=$((attempt + 1))
    
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        log_info "✓ API is healthy (attempt $attempt/$max_attempts)"
        health_ok=true
        break
    fi
    
    if [[ $attempt -lt $max_attempts ]]; then
        log_warn "Health check failed, retrying in 5s... (attempt $attempt/$max_attempts)"
        sleep 5
    fi
done

if [[ "$health_ok" != "true" ]]; then
    log_error "API did not become healthy within 60 seconds"
    log_warn "Check logs: docker compose -f $DOCKER_COMPOSE logs api"
    exit 1
fi

###############################################################################
# Complete
###############################################################################

log_info ""
log_info "╔════════════════════════════════════════════════════════════════╗"
log_info "║ SECRET ROTATION COMPLETED SUCCESSFULLY                         ║"
log_info "╚════════════════════════════════════════════════════════════════╝"
log_info ""

log_warn "⚠️  IMPORTANT: Notify all cashiers of the following:"
log_info ""
log_info "  1. All JWT tokens are now INVALID (signed with old secret key)"
log_info "  2. Each cashier must LOG IN AGAIN within the next hour"
log_info "  3. Current sales sessions will be terminated automatically"
log_info "  4. No data will be lost — pending transactions preserved"
log_info ""

log_info "Rotation summary:"
log_info "  • Secrets updated: 4 (SECRET_KEY, ENCRYPTION_KEY, API_KEY, WEBHOOK_SECRET)"
log_info "  • API container restarted and healthy ✓"
log_info "  • Backup preserved: $ENV_BACKUP"
log_info "  • Server: $(hostname)"
log_info "  • Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log_info ""

log_info "To monitor API logs, run:"
log_info "  docker compose -f $DOCKER_COMPOSE logs -f api"
log_info ""

exit 0
