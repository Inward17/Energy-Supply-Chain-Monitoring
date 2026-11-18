# Technical Debt Register

Known gaps, why they exist, and what "done" looks like. Resolved items stay
listed briefly so the history is visible.

## Open

### P1: War Room brief calls Gemini in the request path

`POST /api/orchestrator/war-room` still calls Gemini synchronously, the one
exception to the Shadow Cache rule.

Mitigated (Nov 2026): briefs are cached 30 min per input set; the endpoint is
rate-limited (5/client, 30 global per hour); a 503 retries once on
`GEMINI_FALLBACK_MODEL`; the UI renders the deterministic brief first and the
narrative after, so a slow or failed call never blocks the page.

Done when: briefs are generated in the background and the endpoint never waits
on the provider.

### P1: Neo4j AuraDB instance lost

Production logs show the Aura host no longer resolves (the free instance was
paused and deleted). The API falls back to seed data, so Reroute still works,
but graph updates (PortWatch congestion) have nowhere to go.

Done when: a new instance is created, `NEO4J_*` is updated in Render and the
GitHub secrets, and the hourly ingestion job keeps it active.

### P2: Neon branch per PR returns HTTP 412

Backend CI's "create Neon branch" step fails with 412; CI falls back to a
throwaway Postgres container, so tests still run, but not against
production-like data. `continue-on-error` hides it; check the job summary.

### P2: No API authentication

Endpoints are public and protected only by CORS (browsers), bounded inputs and
rate limits. Limits are in-process memory: they reset on restart and are not
shared across instances. Fine for one Render instance; move to Redis or
Postgres before scaling out, and put expensive routes behind auth if usage
grows.

### P2: Model simplifications

- SDI is capped when AIS is down (the live vessel weight is not redistributed;
  backtests do redistribute it).
- Backtest days without headlines score ~25 instead of carrying the last
  value forward.
- SPR assumes a 100 % full reserve (stated in the UI); chokepoint import shares
  are static 2024 values, and Gibraltar's (0.08) is an estimate.
- Malacca and the Cape cannot be restricted by the route engine; routes are
  verified by geometry (staying out of a box around the passage). A route that
  must cross one is `unverified`, ranked below verified ones and never
  recommended; its static detour (Malacca 4 d, Cape none) is a rough estimate.
- Supplier risk matches countries by text, not entity resolution.
- The sanctioned-source list is a country list, not sanctions screening.

### P3: No real-device testing; logo pending

Mobile layouts are checked with Playwright phone emulation only.

## Resolved

- **Strict TypeScript** (Nov 2026): `ignoreBuildErrors` removed; `tsc --noEmit`
  runs in Frontend CI.
- **Dashboard GET paths** call no external APIs: Brent/BOAT statistics read
  the local cache, and SDI snapshots are written by the worker.
- **Stale production data** (Nov 2026): ingestion moved to an hourly GitHub
  Actions job, independent of the Render instance sleeping.
- **Reroute route verification** (Nov 2026): lead times use the route that
  avoids the blocked passage; rows state how the route was established.

## Operational notes

**Sentinel Gemini usage.** Each ingestion run makes one Gemini call for a
batch of up to 10 headlines. Backtests and War Room briefs use Gemini
separately and should be budgeted independently.

**Backtest vessel term.** Historical AIS does not exist, so backtests
redistribute the vessel weight (`w2`) proportionally across the other three
signals. The historical index is a 3-signal composite; the live one is 4-signal.
