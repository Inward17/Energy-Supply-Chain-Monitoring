#!/usr/bin/env bash
# =============================================================================
# scripts/restore_seed_data.sh
# Restore Energy Supply Chain Resilience OS seed data into Postgres.
# Run this ONCE after database creation and BEFORE starting cron_worker.py.
#
# Usage:
#   bash scripts/restore_seed_data.sh
#
# Reads DB credentials from backend/.env (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD).
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DUMP_FILE="$REPO_ROOT/seed/postgres_dump.sql"
ENV_FILE="$REPO_ROOT/backend/.env"

# ── Load .env ────────────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Copy backend/.env.example to backend/.env and fill in your credentials."
  exit 1
fi

# Parse key=value pairs (skip comments and blanks)
while IFS='=' read -r key value; do
  [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
  value="${value%%#*}"      # strip inline comments
  value="${value// /}"      # strip spaces
  export "$key=$value"
done < "$ENV_FILE"

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-energy_resilience}"
DB_USER="${DB_USER:-postgres}"
export PGPASSWORD="${DB_PASSWORD:-}"

# ── Pre-flight check ─────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " Energy Supply Chain Resilience OS — Seed Data Restore"
echo "============================================================"
echo " Target: $DB_USER@$DB_HOST:$DB_PORT/$DB_NAME"
echo " Dump:   $DUMP_FILE"
echo "============================================================"

if [[ ! -f "$DUMP_FILE" ]]; then
  echo "ERROR: Seed file not found at $DUMP_FILE"
  exit 1
fi

# Test connection
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1 || {
  echo "ERROR: Cannot connect to Postgres. Ensure Postgres is running and credentials in backend/.env are correct."
  echo "       If using Docker: run 'docker-compose up -d' first."
  exit 1
}

# ── Schema ────────────────────────────────────────────────────────────────────
# The dump is data-only. Schema must exist first.
# init_schema() is normally called by cron_worker.py/api.py on startup,
# but we apply seed/schema.sql here so this script is fully self-contained.
SCHEMA_FILE="$REPO_ROOT/seed/schema.sql"

echo ""
echo "Applying database schema..."
if [[ -f "$SCHEMA_FILE" ]]; then
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$SCHEMA_FILE" --quiet
  echo "  Schema OK."
else
  echo "  seed/schema.sql not found; attempting Python init_schema() fallback..."
  cd "$REPO_ROOT/backend"
  python -c "
import sys; sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv('.env', override=True)
from src.database.postgres_db import init_schema; init_schema()
print('  Schema OK.')
" || { echo "ERROR: Could not initialise schema."; exit 1; }
fi

# ── Restore data ──────────────────────────────────────────────────────────────
echo ""
echo "Restoring seed data..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$DUMP_FILE" --quiet

# ── Verify row counts ─────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " Verification — Row Counts After Restore"
echo "============================================================"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT 'risk_events'          AS table_name, COUNT(*) AS rows FROM risk_events
UNION ALL
SELECT 'risk_events_backtest' AS table_name, COUNT(*) AS rows FROM risk_events_backtest
UNION ALL
SELECT 'market_prices'        AS table_name, COUNT(*) AS rows FROM market_prices
ORDER BY table_name;
"

echo ""
echo "============================================================"
echo " Seed restore complete."
echo " NOTE: Neo4j seeds automatically on first cron_worker.py run."
echo " Next step: start cron_worker.py, then api.py."
echo "============================================================"
echo ""
