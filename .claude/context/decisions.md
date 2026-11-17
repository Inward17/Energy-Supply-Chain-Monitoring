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

- SPR: site capacities (MMT × 7.33) are the source of truth; total derived
  (39.1 MB). Levers ramp in (3/7/14 d) and a 50%-effective pessimistic case
  is returned with an `assumptions` list the UI shows beside the result.
- Reroute: dropdown labels "Name (Country)" are canonicalised; unknown
  refinery → 422 (used to silently route everything to Jamnagar). Supplier
  risk uses the Modeler's age decay. `ranking_mode=balanced` sorts by composite.
- `CF-Connecting-IP` is safe to trust in prod: Cloudflare returns 403 to any
  request that sets it (verified against Render, Nov 2026).
- Frontend fetches time out (60 s, 90 s for war-room); Cloudflare builds fail
  if `NEXT_PUBLIC_API_URL` is missing or localhost.

- Neo4j old-schema migration deletes only APP_LABELS (Chokepoint, ExportPort,
  Refinery, CrudeGrade) — the database may be shared.
- SPR arrival day is fractional (draw and refill split on the arrival day);
  refill rate `replenish_share` (default 50% of disrupted volume) is a request
  field and listed in assumptions.
- risk_events.sources_verified: FALSE when Sentinel fell back to the whole
  batch; UI labels those links "Batch context".
- Sanctioned suppliers are labelled (`sanctioned` on reroute rows), not
  filtered server-side: exclusions stay a user choice; a country list is not
  sanctions screening.
- Reroute lead times come from the route that avoids the blocked passage
  (searoute restriction) whenever one exists; rows carry `route_basis`
  verified / unverified (no restriction: Malacca, Cape, LOOP → static detour) /
  estimated (no coordinates). Neo4j-down fallback is built from seed ports, so
  it has coordinates and real per-port routes.

## Open items
- Neon branch creation returns **HTTP 412** in CI (cause unconfirmed; CI falls
  back to a container). `continue-on-error` hides it — check the job summary.
- No auth on the API (rate limits only). `/docs` is public.
- SDI is capped when AIS is down (vessel weight not redistributed live).
- Reroute options often share one landed cost/lead time (distance fallback).
- SPR assumes a 100% full reserve (stated in UI); import shares are static 2024 values.
- Backtest days with no headlines score ~25 (should carry forward).
- Logo on hold (concepts on a Claude Design canvas). Light theme not designed
  on canvas, only mapped in code. No real-device testing yet.
- Render free tier sleeps → stale data unless a pinger is set up.
