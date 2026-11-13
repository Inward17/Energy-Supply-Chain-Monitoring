# Decisions and known gaps

## Why things are the way they are
- `/healthz` touches no DB: pingers would otherwise keep Neon awake.
- Hourly cron, in-process backtests, no polling: Neon bills compute-hours.
- CORS never `*`: endpoints are unauthenticated and spend Gemini quota.
- Spend controls (`src/utils/rate_limit.py`): war-room 5/client + 30 global
  per hour, backtest 2/client + 4 global per hour, models 30/min. In-memory,
  single-instance. War Room briefs cached 30 min by inputs.
- `httpx` logger at WARNING: NewsData/GNews keys are query params.
- DB read helpers raise `DatabaseUnavailable` → API 503 (outage ≠ empty data).
- Public error text is fixed strings only (`_INTERNAL_ERROR`, backtest categories).
- Backtest events are a closed `Literal` set.
- Exact dependency pins (`requirements.txt`); Dependabot proposes bumps.
- Frontend is a static export: CSP needs `'unsafe-inline'` scripts (Next
  bootstrap + theme script). `connect-src` hard-codes the Render URL.
- Neon/GitHub Actions that get secrets are pinned to commit SHAs.
- Leaflet colours resolved from CSS vars via `cssColor()` (SVG attrs).
- Hash routing (`#page`) — static export, no server routes.

- Ingestion runs in GitHub Actions (`ingest.yml`), not on Render: the free
  instance sleeps and AISStream 429s Render's shared IPs. AIS retries 429 with
  30/90/180 s backoff. Gemini 503 falls back to `GEMINI_FALLBACK_MODEL` once.
- google-genai held at 2.x: 3.0 defaults to API v1 where `gemini-flash-latest` 404s.

## Open items
- Neon branch creation returns **HTTP 412** in CI (cause unconfirmed; CI falls
  back to a container). `continue-on-error` hides it — check the job summary.
- No auth on the API (rate limits only). `/docs` is public.
- SDI is capped when AIS is down (vessel weight not redistributed live).
- Reroute options often share one landed cost/lead time (distance fallback).
- SPR assumes a 100% full reserve; import shares are static 2024 values.
- Backtest days with no headlines score ~25 (should carry forward).
- Logo on hold (concepts on a Claude Design canvas). Light theme not designed
  on canvas, only mapped in code. No real-device testing yet.
- Render free tier sleeps → stale data unless a pinger is set up.
