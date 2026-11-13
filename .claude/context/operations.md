# Operations

## Local
- Postgres 17 runs as a Windows service (db `energy_resilience`); Neo4j via
  Neo4j Desktop (optional — code falls back when it's down).
- `.claude/launch.json`: `backend` (:8000, RUN_WORKER=1), `frontend` (:3000),
  `frontend-legacy` (:3001). All point at the same backend.
- Manual: `cd backend && venv/Scripts/python.exe -m uvicorn api:app --port 8000`
  · `cd frontend && npm run dev` · one ingestion pass: `python cron_worker.py --once`.

## Tests
- Backend: `cd backend && venv/Scripts/python.exe -m pytest -q` (uses `backend/.env` DB).
- Frontend: `npm run typecheck` · `NEXT_PUBLIC_API_URL=http://127.0.0.1:9 npm run build`
  · `npm run test:e2e` (serves `out/` on :4173 via Python http.server).

## Deploy
- **Cloudflare Pages**: root `frontend`, `npm run build`, output `out`. Vars
  (Production *and* Preview): `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_CARTO_KEY`.
  Live: https://energy-supply-chain.pages.dev
- **Render**: Docker (`backend/Dockerfile`, py3.13), `RUN_WORKER=1`,
  `CORS_ORIGINS`, `CORS_ORIGIN_REGEX=^https://([a-z0-9-]+\.)?energy-supply-chain\.pages\.dev$`,
  `DB_*` + `DB_SSLMODE=require`, `NEO4J_*`, Gemini/news/AIS keys. Free tier
  sleeps — needs an external pinger on `/healthz`. Auto-deploy "after CI passes".
  API: https://energy-supply-chain-backend.onrender.com
- **Neon**: db `neondb`, role `neondb_owner` (project ID in GitHub var `NEON_PROJECT_ID`).

## GitHub (`Inward17/Energy-Supply-Chain-Monitoring`)
- Workflows: `frontend-ci` (job `verify`), `backend-ci` (job `test`, Neon
  branch `ci/pr-<n>` per PR with Postgres-container fallback), `neon-cleanup`,
  `codeql`, `ingest` (hourly `cron_worker.py --once --with ais[,portwatch,retention]`
  against Neon; needs DB_*/Gemini/news/AIS/NEO4J_* secrets; Render then runs `RUN_WORKER=0`). Dependabot weekly. GitGuardian + Cloudflare apps installed.
- Secrets/vars: `NEON_API_KEY` (secret), `NEON_PROJECT_ID` (var).
- Required checks to add after first runs: `verify`, `test`.
- Full walkthrough: `docs/github-workflow.md`.

## Key env vars (`backend/.env.example` documents all)
`GEMINI_API_KEYS` (comma pool), `GEMINI_MODEL=gemini-flash-latest`,
`GDELT_TIMESPAN=12h`, `CRON_INTERVAL_MINUTES=60`, `AIS_INTERVAL_MINUTES=60`,
`AIS_SNAPSHOT_SECONDS=600`, `BACKTEST_MAX_CONCURRENT=1`,
`NEO4J_RETRY_COOLDOWN_SECONDS=120`.
