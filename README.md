# MERIDIAN — Energy Supply Chain Resilience OS

> **An AI-assisted energy supply chain intelligence platform that turns crisis response into a managed, anticipatory process.**

Built for India's energy security problem: detecting geopolitical disruptions, re-routing crude procurement around blocked chokepoints, projecting Strategic Petroleum Reserve (SPR) depletion, and drafting an executive Emergency Action Plan.

**Live:** <https://energy-supply-chain.pages.dev> · API: `https://energy-supply-chain-backend.onrender.com`

---

## Table of Contents

1. [What This Is](#what-this-is)
2. [Architecture Overview](#architecture-overview)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Data Flow: End-to-End Pipeline](#data-flow-end-to-end-pipeline)
6. [File-by-File Breakdown](#file-by-file-breakdown)
   - [Entry Points](#entry-points)
   - [Ingestion Layer](#ingestion-layer)
   - [Database Layer](#database-layer)
   - [Agent Layer](#agent-layer)
   - [Utilities](#utilities)
7. [Dashboard Pages](#dashboard-pages)
8. [Design System](#design-system)
9. [The Shadow Cache Architecture](#the-shadow-cache-architecture)
10. [Setup & Running](#setup--running)
11. [Environment Variables](#environment-variables)
12. [Deployment, CI and Further Docs](#deployment-ci-and-further-docs)

---

## What This Is

India imports over 85% of its crude oil. Its Strategic Petroleum Reserve holds about **39 million barrels — roughly 7 days of national consumption**. A blockade at the Strait of Hormuz, through which about 40% of India's crude transits, starts a clock the moment it is confirmed.

The platform:

- **Watches** energy news (GDELT, with NewsData / GNews / NewsAPI fallbacks) and scores it with Gemini
- **Detects** shipping anomalies from live AIS vessel telemetry (AISStream.io)
- **Routes** replacement supply around the blockade using a Neo4j knowledge graph and real sea routes
- **Calculates** landed cost and lead time for every alternative, and says when a route could not be verified
- **Projects** how long the SPR lasts, with and without demand-management levers, and the GDP/inflation cost of any gap
- **Drafts** an Emergency Action Plan with Gemini (the deterministic numbers render first; the narrative follows)

Every model states its assumptions next to its result. How each number is calculated is documented in [`docs/algorithms.md`](docs/algorithms.md).

---

## Architecture Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL WORLD                              │
│  GDELT · NewsData · GNews · NewsAPI   AISStream.io   Yahoo Finance   │
│  IMF PortWatch                        Gemini API                     │
└──────────┬─────────────────────┬──────────────────┬─────────────────┘
           ▼                     ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  INGESTION — cron_worker.py, run hourly by GitHub Actions (ingest.yml)│
│  or in-process on the API with RUN_WORKER=1                          │
│  market · freight · news · Sentinel scoring · SDI snapshot · AIS     │
└──────────┬───────────────────────────────────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                 SHADOW CACHE (the only thing the API reads)          │
│  PostgreSQL (Neon in prod)               Neo4j (AuraDB in prod)      │
│  news_cache · risk_events ·              Chokepoint · ExportPort ·   │
│  vessel_telemetry · market_prices ·      Refinery · CrudeGrade ·     │
│  sdi_snapshots · backtest_jobs           SHIPS_THROUGH · EXPORTS     │
└──────────┬───────────────────────────────────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastAPI (api.py) on Render — agents                                 │
│  modeler (SDI) · fixer (reroute) · spr (burn-down) · briefing (LLM)  │
└──────────┬───────────────────────────────────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  MERIDIAN UI — Next.js static export on Cloudflare Pages             │
│  Overview · Threat Map · Risk · Markets · Reroute · SPR · War Room · │
│  History                                                             │
└──────────────────────────────────────────────────────────────────────┘
```

### Core Design Principle: Shadow Cache Architecture

External data APIs are called **only by the ingestion job**. The dashboard reads Postgres and Neo4j, so a GDELT rate limit or an AIS outage shows up as a stale or "no data" feed in the data-health panel, never as a hung page. The one exception is the War Room brief, which calls Gemini on request; it is rate-limited and cached for 30 minutes per scenario.

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| UI | Next.js 16 (static export), React 19, Tailwind CSS 4 | MERIDIAN dashboard, dark + light, desktop + mobile |
| Maps / charts | Leaflet (CARTO or Esri tiles), hand-built SVG charts | Threat map, sparklines, burn-down and SDI charts |
| Backend API | FastAPI + Pydantic | REST API, bounded request schemas, rate limits |
| Intelligence | Gemini (`GEMINI_MODEL`, default `gemini-flash-latest`) | News scoring, War Room brief; falls back to a lighter model on 503 |
| Graph DB | Neo4j | Supply chain knowledge graph |
| Relational DB | PostgreSQL | News, events, prices, vessels, SDI snapshots, backtests |
| ORM/DB | SQLAlchemy + psycopg2 | Connection pooling, query layer |
| Marine routing | `searoute` | Sea-lane distances, with blocked passages restricted |
| Market data | `yfinance` | Brent, Henry Hub, USO, XLE, BOAT (freight proxy) |
| News | GDELT Doc 2.0 + NewsData.io / GNews / NewsAPI | Headlines, with keyed fallbacks when GDELT throttles |
| Vessels | AISStream.io WebSocket | Live tanker positions |
| Resilience | `tenacity` | Exponential backoff on external calls |
| Hosting | Cloudflare Pages · Render · Neon · Neo4j AuraDB | Free-tier production stack |
| CI | GitHub Actions | Frontend/backend CI, CodeQL, hourly ingestion, Dependabot |

---

## Project Structure

```text
energy-supply-chain/
├── backend/                        # Python API, agents and ingestion
│   ├── api.py                      # FastAPI app: routes, CORS, rate limits, error mapping
│   ├── cron_worker.py              # Ingestion pipeline (scheduled, --once, --with ...)
│   ├── run_backtest.py             # Historical replay of past crises
│   ├── Dockerfile                  # Image used by Render
│   ├── requirements.txt            # Exact pins; Dependabot proposes bumps
│   ├── tests/                      # ~180 pytest tests
│   └── src/
│       ├── agents/                 # sentinel, modeler, fixer, spr, briefing
│       ├── database/               # PostgreSQL & Neo4j layers
│       ├── ingestion/              # GDELT, news fallbacks, AIS, market, freight, PortWatch
│       └── utils/                  # constants, metrics, schemas, rate_limit
│
├── frontend/                       # MERIDIAN UI (Next.js static export)
│   ├── app/                        # Layout, pre-paint theme script, globals.css tokens
│   ├── components/m/               # Shell (hash router), data provider, charts, drawer
│   ├── components/m/pages/         # Overview, Threat Map, Risk, Market, Reroute, SPR, War Room, History
│   ├── lib/api.ts                  # Typed API client (timeouts on every request)
│   ├── public/_headers             # CSP and security headers for Cloudflare Pages
│   └── tests/smoke.spec.ts         # Playwright smoke tests (desktop + phone)
│
├── docs/                           # algorithms.md, github-workflow.md, design canvases
├── .github/                        # Workflows, Dependabot, CODEOWNERS, PR template
├── seed/                           # Postgres schema + historical seed data
├── legacy/frontend/                # Previous UI, kept for comparison (not deployed)
├── DEPLOYMENT.md                   # Production runbook
└── TECHNICAL_DEBT.md               # Known gaps and their status
```

---

## Data Flow: End-to-End Pipeline

### Phase 1 — Ingestion (hourly)

```text
yfinance ───────────────► market_trawler / freight_trawler ──► market_prices
GDELT (3 rotating queries) ─► gdelt_collector ──► news_cache
   └─ on 429: NewsData → GNews → NewsAPI (daily quotas tracked in provider_quota)
AISStream WebSocket ────► ais_streamer (600 s window, 429 retry) ──► vessel_telemetry
IMF PortWatch (12 h) ───► portwatch_trawler ──► port congestion on ExportPort nodes
```

### Phase 2 — Intelligence (same run, after ingestion)

```text
news_cache (unprocessed, up to 10)
    ▼
sentinel_agent ──► Gemini ──► risk_events (one row per incident, with its own sources)
    ▼
modeler_agent ──► sdi_snapshots (the canonical SDI timeline)
```

### Phase 3 — User query (on demand, no external calls except the War Room brief)

```text
Blocked chokepoint + destination refinery
    ▼
fixer_agent:   compatible grades → bypassing terminals → restricted sea route
               → landed cost → decayed supplier risk → ranked matrix
    ▼
spr_agent:     shortfall → burn-down with ramping levers → gap + macro impact
    ▼
briefing_agent (War Room only): Gemini Emergency Action Plan, cached 30 min
```

---

## File-by-File Breakdown

### Entry Points

---

#### `api.py` — FastAPI app

Exposes the agents as REST endpoints for the UI.

- Reads only Postgres/Neo4j (the War Room brief is the one Gemini call).
- Requests are Pydantic models with bounded fields; chokepoint names are
  validated against the registry (aliases like "Hormuz" resolve), unknown
  refineries and chokepoints are 422.
- Errors are fixed public strings: 503 when the database is down or a matrix
  is degraded, 500 otherwise; internals never leak.
- Spend controls in `src/utils/rate_limit.py`: War Room 5/client + 30 global
  per hour, backtests 2 + 4 per hour, model endpoints 30 + 300 per minute.
- `/healthz` touches no database so an uptime pinger never keeps Neon awake.

Endpoints: `/healthz`, `/api/metrics/live`,
`/api/risk/{events,events/{id},chokepoints[/{name}],producers[/{name}],sdi-timeline}`,
`/api/market/{prices,vessels}`, `/api/config/{chokepoints,refineries,grades}`,
`POST /api/orchestrator/{reroute,spr,war-room}`, `/api/backtest/{jobs,trigger,{event}}`.

---

#### `cron_worker.py` — Ingestion pipeline

| Job | Cadence | Steps |
|---|---|---|
| Cycle | `CRON_INTERVAL_MINUTES` (60) | market → freight → news → Sentinel → SDI snapshot |
| AIS | `AIS_INTERVAL_MINUTES` (60) | AIS snapshot → SDI snapshot |
| PortWatch | 12 h | port congestion |
| Retention | 24 h | trim old vessel telemetry |

- Each scheduled step runs in its own thread with a per-step lock, so one
  stalled API cannot block the others; a cross-process file lock stops two
  workers running at once.
- `--once` runs one cycle and exits; `--once --with ais,portwatch,retention`
  adds the timer jobs (this is what the GitHub Actions `ingest` workflow runs).
- `--backfill` loads 24 h of news.
- With `RUN_WORKER=1` the API runs the same scheduler in-process.

---

### Ingestion Layer

---

#### `src/ingestion/gdelt_collector.py` — GDELT News Collector

Queries the **GDELT Doc 2.0 API** (free, no auth) for energy-relevant news.

- **Credibility tiering** prioritises high-credibility global and industry sources.
- **Deduplication** inserts only new URLs (`ON CONFLICT DO NOTHING`).
- **Rate limiting:** GDELT throttles hard per IP. A 429 is *not* retried
  in-cycle (that extends the block); the keyed providers in
  `news_providers.py` cover the gap and the next run retries.
- **Query rotation:** three queries alternate across runs — maritime
  chokepoints, producer-nation supply events, and physical disruption (storm /
  fire / piracy / strike). Without the third, four of the Sentinel's nine
  disruption types were unreachable.

---

#### `src/ingestion/ais_streamer.py` — AIS Vessel Telemetry

Collects tanker positions from **AISStream.io** in six strategic bounding boxes.

| Region | Geographic Area |
|---|---|
| Strait of Hormuz | 23°–28°N, 55°–59°E |
| Bab-el-Mandeb | 11°–15°N, 41°–46°E |
| Suez Canal | 28°–32°N, 31°–34°E |
| Strait of Malacca | 2°S–6°N, 100°–106°E |
| Turkish Straits | 40.5°–41.5°N, 28.5°–30°E |
| Cape of Good Hope | 36°–32°S, 17°–21°E |

- Collects for `AIS_SNAPSHOT_SECONDS` (600 s). Ship *type* arrives only in
  Type-5 messages broadcast about every 6 minutes, so shorter windows classify
  few vessels. Learned types persist in `vessel_type_registry`.
- An HTTP 429 at the handshake is retried after 30 / 90 / 180 s instead of
  losing the window.
- Filters invalid coordinates and labels each vessel with its region.

---

#### `src/ingestion/market_trawler.py` and `freight_trawler.py`

`yfinance` OHLCV for `BZ=F` (Brent, the primary signal), `NG=F`, `USO`, `XLE`,
and `BOAT` (Breakwave dry-bulk shipping ETF), used as the freight-stress proxy. 60 days of history
per run; `get_brent_rolling_stats()` gives the 30-day mean and σ for the SDI.

---

### Database Layer

---

#### `src/database/postgres_db.py` — PostgreSQL

SQLAlchemy pool (`pool_size=5, max_overflow=10`). `init_schema()` is
idempotent (`CREATE TABLE IF NOT EXISTS` plus `ADD COLUMN IF NOT EXISTS`
migrations) and runs on every boot.

| Table | Purpose |
|---|---|
| `news_cache` | Headlines; `processed` controls Sentinel batching |
| `risk_events` | Scored incidents: type, severity, confidence, chokepoints (direct/indirect), producers, summary, `source_urls`, `sources_verified` |
| `vessel_telemetry` / `vessel_type_registry` | AIS positions; learned ship types |
| `market_prices` | OHLCV per ticker |
| `sdi_snapshots` | Canonical SDI timeline written by the worker |
| `backtest_jobs`, `risk_events_backtest` | Historical replay jobs and their events |
| `provider_quota` | Daily usage of the keyed news providers |

Read helpers raise `DatabaseUnavailable` on connection failure, which the API
maps to 503, so an outage is never shown as "no data".

---

#### `src/database/neo4j_graph.py` — Neo4j Knowledge Graph

```text
(ExportPort) -[:SHIPS_THROUGH]-> (Chokepoint)
(ExportPort) -[:EXPORTS]-------> (CrudeGrade)
```

Seeded from code with `MERGE` (idempotent): 8 chokepoints, 12 export
terminals, 20 refineries, 20 crude grades. An old-schema migration removes
only this app's labels, never the whole database. With Neo4j unreachable, the
same data is served from the seed lists after a 120 s cooldown, so the Reroute
page keeps working.

---

### Agent Layer

---

#### `src/agents/sentinel_agent.py` — Risk scoring

Scores up to 10 headlines per run in one Gemini call and writes one event per
incident. Headlines are sanitised and marked untrusted in the prompt; output
fields are validated and clamped. On a 503 it retries once on
`GEMINI_FALLBACK_MODEL`; on a 429 it rotates to the next key in
`GEMINI_API_KEYS`. Events keep only the headlines the model cites; when it
cites none, the batch is attached as context and `sources_verified` is false.

---

#### `src/agents/modeler_agent.py` — SDI and risk matrices

```text
SDI = 100 × (0.50·P_risk + 0.25·ΔD_vessel + 0.10·ΔP_price + 0.15·ΔP_freight)
bands: LOW <30 · MODERATE <50 · ELEVATED <65 · SEVERE <80 · CRITICAL
```

Event risk decays toward a 0.05 baseline with a half-life set by disruption
type, and aggregates by `max`, so one event explains each score. Vessel density
is a self-calibrated tanker share. Details: [`docs/algorithms.md`](docs/algorithms.md) §1–3.

**Important limitation:** the 0.70 producer-to-chokepoint transit discount is
uniform across producer/chokepoint pairs; it does not yet model each producer's
actual route concentration.

---

#### `src/agents/fixer_agent.py` — Reroute

1. Canonicalise the destination (`Rotterdam (Netherlands)` → `Rotterdam`);
   unknown → 422.
2. Find compatible terminals whose graph routes avoid the blockade
   (substitutes within ±4 °API / ±1 % sulphur; two-grade blends).
3. Compute the **restricted** sea route to the chosen refinery whenever the
   route engine can block the passage — rows are labelled `verified`,
   `unverified` (static detour) or `estimated` (no coordinates).
4. Landed cost = Brent + freight premium over the whole voyage.
5. Supplier risk = worst matching event, decayed like the SDI.
6. Rank by `cost`, `speed` or `balanced`:
   `0.35·cost + 0.25·time + 0.25·(1 − risk) + 0.15·(1 − congestion)`.
7. Label sanctioned suppliers (not filtered).

---

#### `src/agents/spr_agent.py` — SPR burn-down

Capacity is derived from the three ISPRL sites (39.1 MB). Shortfall = 5.4 mb/d ×
the blocked chokepoint's explicit import share (unknown chokepoints rejected).
Demand levers ramp in over 3 / 7 / 14 days; a pessimistic case runs them at
50 %. The burn-down handles fractional arrival days and refills at a
configurable share after arrival. The response includes an `assumptions` list
the UI shows beside the result. Details: [`docs/algorithms.md`](docs/algorithms.md) §6.

---

#### `src/agents/briefing_agent.py` — War Room brief

Gemini writes a three-paragraph Emergency Action Plan (situation, procurement,
macro mitigation) from the deterministic outputs. Scenario and refinery labels
are sanitised and delimited as data. Cached 30 minutes per input set.

---

### Utilities

- `src/utils/constants.py` — single source of truth: chokepoint registry and
  aliases, SDI bands, half-lives, VLCC economics, sanctioned-source list.
- `src/utils/metrics.py` — pure functions: SDI, normalisers, price impact,
  resilience score. Weights via `SDI_W1`–`SDI_W4` (must sum to 1.0).
- `src/utils/schemas.py` — bounded request models and the chokepoint validator.
- `src/utils/rate_limit.py` — per-client + global sliding-window limits.

---

## Dashboard Pages

Hash-routed (`#overview`, `#map`, …). Desktop shows a sidebar; phones show a
five-tab bar (Overview · Map · Risk · Markets · Respond) with sub-switches.

| Page | What it shows |
|---|---|
| **Overview** | SDI gauge and band, the four components, what is driving the score, chokepoint dials, alerts, data health. Degrades to the remaining feeds if the SDI feed fails. |
| **Threat Map** | Leaflet map of chokepoint risk and live vessel positions |
| **Risk** | Event feed with filters, SDI timeline, chokepoint and producer matrices |
| **Markets** | Brent vs its 30-day trend, other instruments, freight stress; missing prices read "Unavailable" |
| **Reroute** | Ranked alternative supply with route basis, sanctioned labels and ranking mode |
| **SPR** | Burn-down with levers, pessimistic case, assumptions, reserve sites, macro impact |
| **War Room** | One-click scenario: deterministic brief first, Gemini narrative after; no SPR run when no route exists |
| **History** | Backtests of past crises and lead-time validation |

Every score opens a drill-down drawer naming the event that set it and the
arithmetic behind it:

```text
0.588   severity 0.84  × 0.7 discount  · decayed over 26.2h
        "export routes cross Strait of Hormuz"
```

A data-health panel reports each feed (AIS, news, market, Gemini) as ok,
partial, stale or down, and the shared data provider tracks failures per feed.

---

## Design System

The MERIDIAN design comes from Claude Design canvases (copies in
`docs/design/meridian-v1` and `-v2`).

- **Colour tokens** are CSS variables named after their dark-theme hex
  (`--x-0b0f14`, …) in `app/globals.css`; `html.light` swaps their values.
  Utility classes (`bg-panel`, `text-head`, `bg-crit-soft`, …) map onto them.
- **Theme** is applied by a tiny pre-paint script (`components/m/theme-script.ts`,
  storage key `meridian-v2-theme`) so there is no flash, and toggled from the header.
- **Charts and Leaflet** need concrete colours in SVG attributes, so they resolve
  the CSS variables at runtime with `cssColor()`.
- **Basemap:** CARTO when `NEXT_PUBLIC_CARTO_KEY` is set, otherwise Esri tiles.

---

## The Shadow Cache Architecture

**No external data API is called in the request path.**

```text
Traditional:                     Shadow Cache:
User clicks                      User clicks
  → GDELT (2–10 s)                 → Postgres (<5 ms)
  → Gemini (1–3 s)                 → Neo4j (<10 ms)
  → yfinance (1–3 s)               → render
  → render (~15 s)
```

The ingestion job writes the caches; the API only reads them. The War Room
brief is the deliberate exception, and it is cached and rate-limited.

---

## Setup & Running

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Docker + Docker Compose | 27+ / v2 | Option A — runs everything |
| Python | 3.13 | Option B (matches the Dockerfile and CI) |
| Node.js | 22 (`frontend/.nvmrc`) | Option B |
| PostgreSQL / Neo4j | 17 / 5.x | Option B, if not using Docker for the databases |

---

### Option A — Docker (whole stack)

One command runs Postgres (with historical seed data), Neo4j, the API and the
UI. Every port binds to `127.0.0.1` only.

```bash
git clone <repo-url>
cd energy-supply-chain
cp backend/.env.example backend/.env
```

Set at least `DB_PASSWORD` and `NEO4J_PASSWORD` in `backend/.env` (any values;
the containers are created with them). Add `GEMINI_API_KEY` /
`AISSTREAM_API_KEY` if you want live ingestion.

```bash
docker compose --env-file backend/.env up -d --build
```

| Service | URL | Notes |
|---|---|---|
| UI | http://localhost:3000 | nginx serving the static export |
| API | http://localhost:8000 (`/docs` for OpenAPI) | read-only; seeds Neo4j on first boot |
| Neo4j Browser | http://localhost:7474 | user `neo4j`, your `NEO4J_PASSWORD` |
| Postgres | localhost:5432 | `seed/schema.sql` + `seed/postgres_dump.sql` load on first boot |

The seed data fills the dashboard immediately. To also run hourly **live
ingestion** (calls Gemini, AIS and news APIs, so it spends their quotas):

```bash
docker compose --env-file backend/.env --profile worker up -d
```

Useful commands:

```bash
docker compose --env-file backend/.env ps          # health of each service
docker compose --env-file backend/.env logs -f backend
docker compose --env-file backend/.env down        # stop (keeps data)
docker compose --env-file backend/.env down -v     # stop and delete the databases
```

Notes:

- `--env-file backend/.env` supplies the `${DB_PASSWORD}`-style values in
  `docker-compose.yml`; the same file is passed into the containers, with
  `DB_HOST` / `NEO4J_URI` overridden to the container network.
- The UI's API URL is compiled in at build time (`NEXT_PUBLIC_API_URL`, default
  `http://localhost:8000`, the API's published port). Changing it needs
  `--build`. To use CARTO tiles, export `NEXT_PUBLIC_CARTO_KEY` before building.
- The UI container sends the same security headers as production except the
  CSP, whose `connect-src` names the production API.
- The `Docker` GitHub Actions workflow builds both images and boots this stack
  on every PR that touches them.

You can also run only the databases and the app natively:
`docker compose --env-file backend/.env up -d postgres neo4j`, then Option B
from "Install dependencies".

---

### Option B — Native

**Databases.** Either `docker compose --env-file backend/.env up -d postgres neo4j`,
or install them yourself:

```bash
# Postgres: create the database and load schema + seed data
psql -U postgres -c "CREATE DATABASE energy_resilience;"
.\scripts\restore_seed_data.ps1      # Windows
bash scripts/restore_seed_data.sh    # Mac/Linux
```

Neo4j 5.x: start it, set the password at http://localhost:7474 to your
`NEO4J_PASSWORD`. The graph seeds itself when the API starts.

> Without the seed restore the dashboard is empty until ingestion has run for
> a few hours.

**Install dependencies**

```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1          # Windows
# source venv/bin/activate           # Mac/Linux
pip install -r requirements.txt

cd ../frontend
npm install
```

**Run**

```bash
# API (seeds Neo4j on first boot)
cd backend && uvicorn api:app --reload --port 8000

# Ingestion scheduler (optional; calls metered APIs)
cd backend && python cron_worker.py          # or: python cron_worker.py --once

# UI
cd frontend && npm run dev                   # http://localhost:3000
```

The previous UI can run against the same API for comparison:
`cd legacy/frontend && npm run dev -- -p 3001`.

---

## Environment Variables

Backend configuration lives in `backend/.env` (copy `backend/.env.example`,
which documents every variable). `load_dotenv()` never overrides variables
already set by the host, so platform settings always win over a stray `.env`.

```bash
# ── PostgreSQL ────────────────────────────────────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME=energy_resilience
DB_USER=postgres
DB_PASSWORD=your_password
DB_SSLMODE=                  # "require" for Neon

# ── Neo4j ─────────────────────────────────────────────────────────────────
NEO4J_URI=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# ── Gemini ────────────────────────────────────────────────────────────────
# Free key: https://aistudio.google.com/app/apikey
# Without it: Sentinel is off and the War Room brief shows a placeholder;
# historical data and every deterministic model still work.
GEMINI_API_KEY=your_gemini_api_key
GEMINI_API_KEYS=             # optional comma-separated pool; a 429 rotates keys
GEMINI_MODEL=gemini-flash-latest
GEMINI_FALLBACK_MODEL=gemini-flash-lite-latest   # tried once on 503

# ── News fallback providers (used when GDELT rate-limits) ─────────────────
NEWSDATA_API_KEY=            # 200 req/day, real-time
GNEWS_API_KEY=               # 100 req/day, ~12h delay
NEWSAPI_API_KEY=             # 100 req/day, ~24h delay, non-commercial only
GDELT_TIMESPAN=12h

# ── AISStream.io ───────────────────────────────────────────────────────────
AISSTREAM_API_KEY=your_aisstream_key   # free at https://aisstream.io

# ── API server ─────────────────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:3000     # comma-separated exact origins
CORS_ORIGIN_REGEX=                     # e.g. Cloudflare preview URLs
RUN_WORKER=0                           # 1 = run the ingestion scheduler in the API process
TRUSTED_PROXY=cloudflare               # client-IP header for rate limits; "none" = TCP peer only

# ── SDI weights (must sum to 1.0) ─────────────────────────────────────────
SDI_W1=0.50    # geopolitical risk
SDI_W2=0.25    # vessel density
SDI_W3=0.10    # Brent deviation
SDI_W4=0.15    # freight stress

# ── Worker ─────────────────────────────────────────────────────────────────
CRON_INTERVAL_MINUTES=60
AIS_INTERVAL_MINUTES=60
AIS_SNAPSHOT_SECONDS=600     # must exceed the ~360 s AIS Type-5 period
BACKTEST_MAX_CONCURRENT=1
```

Frontend (`frontend/.env.local`, or build variables on Cloudflare Pages —
they are baked into the static bundle at build time):

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000   # production builds fail if this is missing or localhost
NEXT_PUBLIC_CARTO_KEY=                      # optional; Esri tiles are used without it
```

---

## Deployment, CI and Further Docs

| Document | Covers |
|---|---|
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Production runbook: Cloudflare Pages, Render, Neon, AuraDB, hourly ingestion, free-tier budgets |
| [`docs/github-workflow.md`](docs/github-workflow.md) | PRs, required checks, CI workflows, Neon branch per PR, Dependabot, CodeQL |
| [`docs/algorithms.md`](docs/algorithms.md) | Every formula and constant behind the numbers on screen |
| [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md) | Known gaps and their status |

Checks to run before opening a PR (CI runs the same). Tests refuse a remote
`DB_HOST` unless `TEST_DB_ALLOW_REMOTE=1`, and never use the configured Neo4j
(set `TEST_NEO4J_URI` for a dedicated test graph):

```bash
cd backend && python -m pytest -q
cd frontend && npm run typecheck && NEXT_PUBLIC_API_URL=http://127.0.0.1:9 npm run build && npm run test:e2e
```

---

## License

Released under the [MIT License](LICENSE).
