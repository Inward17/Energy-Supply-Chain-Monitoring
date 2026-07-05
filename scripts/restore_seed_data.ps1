# =============================================================================
# scripts\restore_seed_data.ps1
# Restore Energy Supply Chain Resilience OS seed data into Postgres.
# Run this ONCE after database creation and BEFORE starting cron_worker.py.
#
# Usage (from repo root):
#   .\scripts\restore_seed_data.ps1
#
# Reads DB credentials from backend\.env
# =============================================================================

$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent $ScriptDir
$DumpFile   = Join-Path $RepoRoot "seed\postgres_dump.sql"
$EnvFile    = Join-Path $RepoRoot "backend\.env"
$BackendDir = Join-Path $RepoRoot "backend"
$Python     = Join-Path $BackendDir "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"   # fall back to system Python
}

# ── Load .env ────────────────────────────────────────────────────────────────
if (-not (Test-Path $EnvFile)) {
    Write-Error "ERROR: $EnvFile not found. Copy backend\.env.example to backend\.env and fill in your credentials."
    exit 1
}

$envVars = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#")) {
        $parts = $line.Split("=", 2)
        if ($parts.Length -eq 2) {
            $key   = $parts[0].Trim()
            $value = $parts[1].Trim().Split("#")[0].Trim()   # strip inline comments
            $envVars[$key] = $value
        }
    }
}

$DB_HOST = if ($envVars["DB_HOST"]) { $envVars["DB_HOST"] } else { "localhost" }
$DB_PORT = if ($envVars["DB_PORT"]) { $envVars["DB_PORT"] } else { "5432" }
$DB_NAME = if ($envVars["DB_NAME"]) { $envVars["DB_NAME"] } else { "energy_resilience" }
$DB_USER = if ($envVars["DB_USER"]) { $envVars["DB_USER"] } else { "postgres" }
$env:PGPASSWORD = if ($envVars["DB_PASSWORD"]) { $envVars["DB_PASSWORD"] } else { "" }

# ── Pre-flight ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================"
Write-Host " Energy Supply Chain Resilience OS -- Seed Data Restore"
Write-Host "============================================================"
Write-Host " Target : $DB_USER@${DB_HOST}:${DB_PORT}/$DB_NAME"
Write-Host " Dump   : $DumpFile"
Write-Host "============================================================"

if (-not (Test-Path $DumpFile)) {
    Write-Error "ERROR: Seed file not found at $DumpFile"
    exit 1
}

# Test Postgres connection
try {
    $result = & psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT 1;" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql returned exit code $LASTEXITCODE" }
} catch {
    Write-Host ""
    Write-Host "ERROR: Cannot connect to Postgres."
    Write-Host "  Make sure Postgres is running (or run: docker-compose up -d)"
    Write-Host "  and that DB_PASSWORD in backend\.env is correct."
    exit 1
}

# ── Schema ────────────────────────────────────────────────────────────────────
$SchemaFile = Join-Path $RepoRoot "seed\schema.sql"

Write-Host ""
Write-Host "Applying database schema..."
if (Test-Path $SchemaFile) {
    & psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f $SchemaFile -q
    if ($LASTEXITCODE -ne 0) { Write-Error "Schema apply failed."; exit 1 }
    Write-Host "  Schema OK."
} else {
    Write-Host "  seed\schema.sql not found; falling back to Python init_schema()..."
    Push-Location $BackendDir
    try {
        & $Python -c @"
import sys; sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv('.env', override=True)
from src.database.postgres_db import init_schema; init_schema()
print('  Schema OK.')
"@
        if ($LASTEXITCODE -ne 0) { throw "Schema init failed" }
    } catch {
        Pop-Location
        Write-Error "ERROR: Could not initialise schema. Check: pip install -r requirements.txt"
        exit 1
    }
    Pop-Location
}

# ── Restore ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Restoring seed data..."
& psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f $DumpFile -q
if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR: psql restore failed."
    exit 1
}

# ── Verify ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================"
Write-Host " Verification -- Row Counts After Restore"
Write-Host "============================================================"
& psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c @"
SELECT 'risk_events'          AS table_name, COUNT(*) AS rows FROM risk_events
UNION ALL
SELECT 'risk_events_backtest' AS table_name, COUNT(*) AS rows FROM risk_events_backtest
UNION ALL
SELECT 'market_prices'        AS table_name, COUNT(*) AS rows FROM market_prices
ORDER BY table_name;
"@

Write-Host ""
Write-Host "============================================================"
Write-Host " Seed restore complete."
Write-Host " NOTE: Neo4j seeds automatically on first cron_worker.py run."
Write-Host " Next step: start cron_worker.py, then uvicorn api:app --port 8000"
Write-Host "============================================================"
Write-Host ""
