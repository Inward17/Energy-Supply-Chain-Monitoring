# Energy Supply Chain Resilience OS

> **An AI-powered, real-time energy supply chain intelligence platform that turns crisis response into a managed, anticipatory process.**

Built for India's national energy security challenge: detecting geopolitical disruptions, re-routing crude oil procurement, projecting Strategic Petroleum Reserve (SPR) depletion, and generating an executive Emergency Action Plan — all in seconds.

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
7. [Dashboard Tabs](#dashboard-tabs)
8. [The Shadow Cache Architecture](#the-shadow-cache-architecture)
9. [Setup & Running](#setup--running)
   - [Option A — Docker (Recommended)](#option-a--docker-recommended)
   - [Option B — Manual Setup](#option-b--manual-database-setup-without-docker)
10. [Environment Variables](#environment-variables)

---

## What This Is

India imports over 85% of its crude oil. Its Strategic Petroleum Reserves provide roughly **9.5 days of national consumption cover**. A blockade at the Strait of Hormuz — through which 40% of India's crude transits — creates a clock that starts ticking the moment the blockade is confirmed.

This platform is a **multi-agent AI command centre** that:

- **Watches** global news in real time (GDELT API → Gemini 2.5 Flash scoring)
- **Detects** shipping anomalies via live AIS vessel telemetry (AISStream.io)
- **Routes** replacement shipments around the blockade through a Neo4j knowledge graph
- **Calculates** the exact financial cost and lead time of every alternative
- **Projects** how many days India's SPR survives, and the GDP/inflation shock if reserves run dry
- **Generates** a boardroom-ready Emergency Action Plan using Gemini

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL WORLD                              │
│   GDELT News API    AISStream.io WebSocket    Yahoo Finance API     │
└──────────┬───────────────────┬───────────────────┬─────────────────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     INGESTION LAYER (cron_worker.py)                │
│  gdelt_collector.py    ais_streamer.py    market_trawler.py         │
│  (News Headlines)      (Vessel Positions) (OHLCV Prices)            │
└──────────┬───────────────────┬───────────────────┬─────────────────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 LOCAL SHADOW CACHE (Zero-latency reads)             │
│  PostgreSQL                               Neo4j Graph DB            │
│  ├── news_cache                           ├── Chokepoint nodes      │
│  ├── risk_events                          ├── ExportPort nodes      │
│  ├── vessel_telemetry                     ├── Refinery nodes        │
│  └── market_prices                        ├── CrudeGrade nodes      │
│                                           └── SHIPS_THROUGH edges   │
└──────────┬────────────────────────────────────┬────────────────────┘
           │                                    │
           ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        AGENT LAYER                                  │
│                                                                     │
│  sentinel_agent.py      modeler_agent.py     fixer_agent.py        │
│  (Gemini: Score News)   (SDI Math)           (Graph Rerouting)     │
│                                                                     │
│  spr_agent.py           briefing_agent.py                          │
│  (SPR Burn-Down)        (Gemini: Write Brief)                      │
└──────────┬─────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 REACT / NEXT.JS DASHBOARD (UI)                      │
│  Tab 1: Threat Map   Tab 2: Risk Intelligence   Tab 3: Market Pulse │
│  Tab 4: Reroute Matrix   Tab 5: SPR Optimizer   Tab 6: War Room     │
└─────────────────────────────────────────────────────────────────────┘
```

### Core Design Principle: Shadow Cache Architecture

Every external API is hit **only in the background** (cron_worker.py). The React UI **never blocks on a live API call**. This means:
- The dashboard loads in milliseconds regardless of external API state
- A GDELT rate-limit or AIS outage is invisible to the end user
- All agents read from local Postgres/Neo4j — zero latency, zero cost

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| UI | React (Next.js) | Interactive dashboard, rich data visualizations (Recharts, Tailwind) |
| Backend API | FastAPI | REST bridge connecting the UI to the intelligence agents |
| Intelligence | Google Gemini 2.5 Flash | News scoring, Executive Briefing |
| Graph DB | Neo4j | Supply chain routing knowledge graph |
| Relational DB | PostgreSQL | Time-series cache (news, prices, vessels) |
| ORM/DB | SQLAlchemy + psycopg2 | Connection pooling, query abstraction |
| Marine Routing | `searoute` | Real nautical distance calculations |
| Financial Data | `yfinance` | Brent Crude, NG, USO, XLE prices |
| News Data | GDELT Doc 2.0 API | Primary headline source (free, no auth) |
| News Fallback | NewsData.io / GNews / NewsAPI | Take over when GDELT rate-limits |
| Vessel Data | AISStream.io WebSocket | Live AIS tanker positions |
| Resilience | `tenacity` | Exponential backoff on all external APIs |
| Scheduling | `schedule` | Cron loop for the ingestion pipeline |

---

## Project Structure

```text
energy-supply-chain/
│
├── backend/                        # Python API and AI Agents
│   ├── api.py                      # FastAPI bridge to the UI
│   ├── cron_worker.py              # Background pipeline scheduler (Shadow Cache heartbeat)
│   ├── requirements.txt            # Python dependencies
│   ├── .env                        # All backend secrets and tuning knobs (never committed)
│   └── src/
│       ├── agents/                 # Logic agents (fixer, modeler, sentinel, spr, briefing)
│       ├── database/               # PostgreSQL & Neo4j driver layer
│       ├── ingestion/              # Data trawlers (GDELT, AIS, yfinance)
│       └── utils/                  # Domain constants and math metrics
│
└── frontend/                       # React/Next.js User Interface
    ├── components/                 # Reusable UI widgets and tabs
    ├── lib/                        # API fetcher utility (api.ts)
    ├── app/                        # Next.js pages and routing
    └── package.json                # Node dependencies
```

---

## Data Flow: End-to-End Pipeline

### Phase 1 — Ingestion (runs every 60 minutes via cron_worker.py)

```text
GDELT API ──────────────► gdelt_collector.py ──► news_cache (Postgres)
                           (50 articles / 3-day window)

AISStream.io WebSocket ──► ais_streamer.py ──────► vessel_telemetry (Postgres)
                           (120s snapshot per cycle)

Yahoo Finance API ────────► market_trawler.py & ───► price_history (Postgres)
                           freight_trawler.py 
                           (60-day OHLCV history)
```

### Phase 2 — Intelligence (triggered by cron cycle, after ingestion)

```text
news_cache (unprocessed)
    │
    ▼
sentinel_agent.py ──────► Gemini 2.5 Flash ──────► risk_events (Postgres)
                          (batch of 5 headlines)     (region, severity, chokepoints, SDI)
```

### Phase 3 — User Query (on-demand, milliseconds, no external calls)

```text
User selects "Blocked Chokepoint" + "Destination Refinery"
    │
    ▼
fixer_agent.py (5 steps):
  Step 1: Neo4j query ─────────────────────► Refineries compatible with crude grade
  Step 2: Neo4j query ─────────────────────► Export ports that bypass the blockade
  Step 3: Postgres query + VLCC math ──────► Landed Cost (Brent + freight premium)
  Step 4: searoute(port → refinery) ───────► Real nautical distance → lead time (days)
  Step 5: Composite scoring ───────────────► Ranked procurement matrix
    │
    ▼
spr_agent.py:
  Daily shortfall (from chokepoint import share) + lead_time_days
  ────────────────────────────────────────────► Burn-down trajectory (pandas DataFrame)
  ────────────────────────────────────────────► Supply gap days + GDP/inflation impact
    │
    ▼
briefing_agent.py (War Room only):
  Procurement matrix row #1 + SPR outputs
  ────────────────────────────────────────────► Gemini 2.5 Flash
  ────────────────────────────────────────────► 3-paragraph Emergency Action Plan
```

---

## File-by-File Breakdown

### Entry Points

---

#### `api.py` — FastAPI Bridge
The serving layer. Exposes all Python agent logic (fixer, spr, sentinel, briefing) as REST endpoints that the React frontend calls via `fetch()`.

- **Never** makes external network requests directly — all data comes from Postgres/Neo4j
- Provides cleanly-typed JSON responses via Pydantic schemas (e.g. `RerouteRequest`, `WarRoomRequest`)

---

#### `cron_worker.py` — Background Pipeline Scheduler
The engine that keeps the Shadow Cache fresh. Runs in a separate terminal alongside `npm run dev`.

**Pipeline steps** (sequential, every `CRON_INTERVAL_MINUTES` — default 60 min):

| Step | Module | What It Does |
|---|---|---|
| 1 | `market_trawler` | Downloads Brent/NG/XLE/USO OHLCV data |
| 2 | `gdelt_collector` | Fetches last 3 days of energy news headlines |
| 3 | `ais_streamer` | Opens WebSocket, collects vessel positions for 120s |
| 4 | `sentinel_agent` | Sends unprocessed headlines to Gemini for risk scoring |

- Uses an in-process lock (`_running` boolean) to prevent overlapping cycles on Windows
- Logs all steps to both `stdout` and `cron_worker.log`
- `--once` flag for single-pass validation; `--backfill` for 24h news catch-up

---

### Ingestion Layer

---

#### `src/ingestion/gdelt_collector.py` — GDELT News Collector

Queries the **GDELT Doc 2.0 API** (free, no auth) for energy-relevant news.

- **Query**: searches for `"Strait of Hormuz" OR "Suez Canal" OR "crude oil" OR "oil tanker"` etc.
- **Credibility Tiering**: Prioritizes high-credibility global (60%) and industry (20%) sources (e.g., Reuters, Bloomberg, OilPrice).
- **Deduplication**: inserts only new URLs using `ON CONFLICT DO NOTHING`
- **Rate limiting**: GDELT throttles hard per IP. A 429 is *not* retried in-cycle
  (that extends the block); the next scheduled cycle is the retry, and the
  keyed providers in `news_providers.py` cover the gap
- **Query rotation**: three queries alternate across cycles — A (maritime
  chokepoints), B (producer-nation supply events), C (physical disruption:
  storm / fire / piracy / strike). Without C, four of the Sentinel's nine
  disruption types were unreachable
- **Output**: Raw article records stored in `news_cache` with `processed=False`

---

#### `src/ingestion/ais_streamer.py` — AIS Vessel Telemetry Collector

Connects to **AISStream.io WebSocket** and collects tanker positions in 6 strategic bounding boxes.

**Bounding boxes monitored:**

| Region | Geographic Area |
|---|---|
| Strait of Hormuz | 23°–28°N, 55°–59°E |
| Bab-el-Mandeb | 11°–15°N, 41°–46°E |
| Suez Canal | 28°–32°N, 31°–34°E |
| Strait of Malacca | 2°S–6°N, 100°–106°E |
| Turkish Straits | 40.5°–41.5°N, 28.5°–30°E |
| Cape of Good Hope | 36°–32°S, 17°–21°E |

- Collects for `AIS_SNAPSHOT_SECONDS` (default 600s) then disconnects cleanly.
  Ship *type* arrives only in Type-5 (ShipStaticData) messages broadcast roughly
  every 6 minutes, while positions arrive every few seconds — a window shorter
  than that classifies only ~window/360 of vessels. Learned types are persisted
  to `vessel_type_registry` so coverage compounds across cycles.
- Filters garbage coordinates (0,0) and validates lat/lon bounds
- Assigns a human-readable `region` label based on which bounding box the vessel is in
- Output stored in `vessel_telemetry` table with MMSI, position, speed, heading

---

#### `src/ingestion/market_trawler.py` — Market Price Fetcher

Downloads OHLCV data for 4 energy tickers via `yfinance` (no API key required).

| Ticker | Instrument |
|---|---|
| `BZ=F` | Brent Crude Futures (primary signal) |
| `NG=F` | Henry Hub Natural Gas Futures |
| `USO` | United States Oil Fund ETF |
| `XLE` | Energy Select Sector SPDR Fund |

- Fetches `MARKET_HISTORY_PERIOD` (60 days) of history on each cron cycle
- `get_brent_rolling_stats()` returns current price, 30-day mean, and std deviation for SDI normalisation

---

### Database Layer

---

#### `src/database/postgres_db.py` — PostgreSQL Abstraction Layer

The local time-series cache. Uses **SQLAlchemy connection pooling** (pool_size=5, max_overflow=10).

**Tables:**

| Table | Schema | Purpose |
|---|---|---|
| `news_cache` | id, url, title, source, fetched_at, processed | Raw GDELT headlines; `processed` flag controls Sentinel batching |
| `vessel_telemetry` | mmsi, vessel_name, lat, lon, speed, heading, region, recorded_at | AIS positions; latest position per MMSI retained |
| `risk_events` | region, disruption_type, severity, affected_chokepoints (JSON), sdi_score, summary, scored_at | Gemini-scored geopolitical events |
| `price_history` | ticker, trade_date, open, close, high, low, volume | OHLCV market data |

**Key operations:**
- `init_schema()` — idempotent `CREATE TABLE IF NOT EXISTS` (safe to call on every boot)
- `upsert_news()` / `upsert_vessel()` / `upsert_price()` — conflict-tolerant bulk inserts
- `fetch_risk_events()` — retrieves latest scored events ordered by `scored_at DESC`
- `fetch_latest_prices()` — returns the most recent close price per ticker

---

#### `src/database/neo4j_graph.py` — Neo4j Knowledge Graph

The spatial reasoning engine. Stores the supply chain topology as a property graph.

**Graph Schema:**

```text
(ExportPort) -[:SHIPS_THROUGH]-> (Chokepoint)
(ExportPort) -[:EXPORTS]-------> (CrudeGrade)
(Refinery)   -[:COMPATIBLE_WITH]-> (CrudeGrade)
(Chokepoint) -[:CONNECTS_TO]---> (Chokepoint)
```

**Seeded with:**
- 8 major maritime chokepoints (with lat/lon, daily flow MB/day)
- 12 crude export terminals (with transit dependencies)
- 20 globally significant refineries (with capacity, lat/lon, API range)
- 17 crude grades (API gravity, sulphur content)

**Key Cypher queries:**
- `find_export_ports_bypassing(chokepoint)` — finds ports whose `SHIPS_THROUGH` edges do NOT include the blocked chokepoint
- `find_alternative_routes(chokepoint)` — returns full route-to-port mapping
- `match_refineries_to_crude(grade)` — returns refineries compatible with a specific API gravity range
- `get_refinery_coords(name)` — returns lat/lon for searoute distance calculation

---

### Agent Layer

---

#### `src/agents/sentinel_agent.py` — Geopolitical Risk Scoring Agent

Uses **Gemini 2.5 Flash** to score batches of news headlines for geopolitical risk.

**Process:**
1. Fetches up to 5 unprocessed headlines from `news_cache`
2. Builds a structured JSON prompt requesting: `region`, `disruption_type`, `severity (0-1)`, a multi-factor `severity_breakdown`, `affected_chokepoints`, `confidence`, and a comprehensive 3-4 sentence `summary`.
3. Validates the response — filters `affected_chokepoints` to only recognised names from `CHOKEPOINTS_SET`
4. Enriches the event with a **Supply Disruption Index (SDI)** score using live Brent pricing
5. Writes the scored event to `risk_events`
6. Marks all processed headlines as `processed=True`

**Rate limit guard:**
- Tracks a rolling 60-second request deque (`_RPM_LIMIT = 15`)
- Sleeps automatically when approaching the free-tier limit
- tenacity retries on transient errors with exponential backoff

---

#### `src/agents/modeler_agent.py` — Deterministic SDI Math Engine

A zero-LLM computation layer. Reads from local Postgres/Neo4j and applies the **SDI formula**:

```text
SDI = w1·P_risk + w2·ΔD_vessel + w3·ΔP_price + w4·ΔP_freight

Where:
  P_risk     = Gemini Sentinel severity score (0–1)
  ΔD_vessel  = tanker-share drop vs a self-calibrated baseline (0–1)
  ΔP_price   = Brent price z-score vs 30-day mean (0–1)
  ΔP_freight = BOAT ETF price z-score vs 30-day mean (0–1)
  w1=0.50, w2=0.25, w3=0.10, w4=0.15  (overridable via SDI_W1/W2/W3/W4 env vars)

Geopolitical risk carries half the index because it is the leading indicator.
At w1=0.40 a severe chokepoint incident could not lift the headline out of the
"moderate" band while markets stayed calm. The reallocation came from the two
market terms rather than vessel density: price and freight are lagging/derived
signals, whereas vessel movement is direct physical evidence.

The composite is also banded (`SDI_BANDS` in constants.py) — LOW / MODERATE /
ELEVATED / SEVERE / CRITICAL — and the dashboard colours the headline from the
band rather than a local threshold.
```

- `compute_current_sdi()` — real-time global risk snapshot for the dashboard header
- `compute_chokepoint_risk_matrix()` — per-chokepoint breakdown with vessel counts and price impact
- `score_alternatives()` — resilience scoring for a set of rerouted alternatives

**Vessel density is self-calibrating.** The baseline for a region is the median
of *its own* recent readings, pulled from the same query as the live value, so
partial AIS coverage biases both sides equally and cancels. It replaced a
hand-maintained table of vessel counts that required ≥70% ship-type coverage to
be trusted — a bar the collector could not clear, leaving 25% of the index
permanently dead.

The measured quantity is **tanker share** (`tankers / typed`), not a corrected
count. A share is invariant to both AIS type coverage and the collector's
snapshot window, whereas a raw count moves with either. On live data it was the
more stable baseline in every region (e.g. Malacca CV 0.76 → 0.42).

*Trade-off:* a uniform collapse of **all** traffic leaves the share unchanged.
This detects the realistic case — tankers rerouting while other shipping
continues — not a total port shutdown.

---

**Important limitation:** The `0.70` producer-to-chokepoint transit-inference
discount is applied uniformly across producer/chokepoint pairs. It does not
yet model each producer's actual route concentration; that refinement awaits a
reliable trade-flow data integration.

---

#### `src/agents/fixer_agent.py` — Adaptive Procurement Orchestrator

The core rerouting engine. Executes a **5-step analysis** for every user query.

**Step 1 — Chemical Constraint:**
Queries Neo4j for refineries compatible with the selected crude grade (by API gravity range). If no match, the grade constraint is widened to include all grades.

**Step 2 — Spatial Traversal:**
Queries Neo4j for export ports whose shipping routes do **not** cross the blocked chokepoint. Uses Cypher path traversal on the `SHIPS_THROUGH` graph.

**Step 3 — Financial Math (Freight Premium):**
```text
Freight Premium ($/bbl) = (VLCC Daily Charter × Conditional Detour Days) / VLCC Cargo Barrels

Conditional Detour Days = 0 if the port's natural route avoids the blockade
                        = N extra days if the port would normally transit the blockade
Landed Cost ($/bbl) = Brent Spot + Freight Premium
```

**Step 4 — Lead Time (Marine Routing):**
Uses the `searoute` library for real nautical distance calculation between the export port and the destination refinery. Converts km → NM → days at VLCC speed (13 knots = 312 NM/day).

**Step 5 — Composite Scoring:**
```text
Composite Score = 0.40 × Cost Score + 0.30 × Time Score + 0.30 × Risk Score

Time Score = 1 - min(lead_time / 45 days, 1)
Cost Score = 1 - min(landed_cost / max_cost, 1)
Risk Score = 1 - dynamic_route_risk (from risk_events DB)
```
Ports are ranked by composite score (or cost/speed only, user-selectable). The top-ranked port is flagged as the recommendation.

---

#### `src/agents/spr_agent.py` — SPR Burn-Down Modeller

Calculates India's **Strategic Petroleum Reserve depletion trajectory** during a supply disruption.

**Inputs:**
- `lead_time_days` — days until the rerouted shipment arrives (from Fixer Agent)
- `blocked_chokepoint` — determines India's daily import shortfall (from `_CHOKEPOINT_IMPORT_SHARE` map)
- `disrupted_volume_mbpd` — optional manual override

**Process:**
1. Computes daily shortfall: `India consumption × chokepoint import share`
2. `SPR Survival Days = SPR Capacity (39 MB) / Daily Shortfall`
3. `Supply Gap = max(0, Lead Time − SPR Survival Days)`
4. Applies **Demand Management Levers** to narrow the gap:
   - Refinery Run-Rate Cut (−15%)
   - Industrial Priority Scheme (−8%)
   - Transport Fuel Rationing (−10%)
5. Builds a day-by-day burn-down DataFrame (baseline vs managed)
6. Computes macro-economic impact: `GDP Hit = Gap Days × 0.035%/day` → USD equivalent at India GDP ≈ $3.7T

**Output:** A complete dict including burn-down DataFrame, demand actions, GDP/inflation impact, and a colour-coded recommendation (green / orange / red).

---

#### `src/agents/briefing_agent.py` — Executive Briefing Agent

Uses **Gemini 2.5 Flash** to write a formal Emergency Action Plan from the deterministic agent outputs.

**Prompt structure:**
- Persona: Chief Intelligence Officer for India's Ministry of Petroleum & Natural Gas
- Context: Crisis name, target refinery, SPR data (survival days, supply gap, macro impact), top reroute (port, grade, lead time, landed cost)
- Output: 3 paragraphs — Situation Assessment → Procurement Directive → Macro-economic Mitigation

Designed to be rendered directly in the War Room tab.

---

### Utilities

---

#### `src/utils/constants.py` — Domain Constants Registry
Single source of truth for all shared domain constants. **All modules import from here** — no magic literals scattered across files.

Covers: canonical chokepoint list, VLCC financial fallbacks, Gemini model name (env-overridable), SDI thresholds, and market data periods.

---

#### `src/utils/metrics.py` — Pure Math Functions
Stateless, no-I/O functions for risk quantification.

| Function | Purpose |
|---|---|
| `supply_disruption_index()` | Weighted SDI formula → score in [0, 100] |
| `normalise_price_delta()` | Z-score Brent price deviation to [0, 1] |
| `normalise_vessel_density_delta()` | Vessel count vs baseline deviation to [0, 1] |
| `estimate_price_impact()` | USD/bbl crude price impact from supply shock |
| `compute_resilience_score()` | Resilience index for a set of rerouted alternatives |
| `flow_weighted_risk()` | Flow-weighted aggregate risk across multiple chokepoints |

Weights (`w1`, `w2`, `w3`, `w4`) are overridable via `SDI_W1`–`SDI_W4` environment variables (must sum to 1.0).

---

## Dashboard Tabs

| # | Tab | Description |
|---|---|---|
| 1 | 🌍 **Threat Map** | Interactive Leaflet map displaying live vessel positions and a chokepoint risk heatmap |
| 2 | 🔴 **Risk Intelligence** | Four equal panels: Sentinel event feed, SDI timeline, chokepoint risk matrix, producer risk matrix |
| 3 | 📈 **Market Pulse** | Brent/NG/XLE charts + 60-day high/low and price-impact KPI cards |
| 4 | 🔀 **Reroute Matrix** | Interactive 5-step procurement analysis — select a blocked chokepoint and destination refinery to get a ranked table of alternative crude sources |
| 5 | 🛢️ **SPR Optimizer** | SPR burn-down simulator with Recharts graph, demand management playbook, and GDP/inflation impact |
| 6 | ⚔️ **War Room** | One-click crisis scenario simulator — selects a scenario, runs the full pipeline, and generates an AI-written Executive Action Plan |
| 7 | ⏮️ **Historical Validation** | Backtest job manager plus lead-time validation against past crises |

### Score drill-downs

Every row in the Sentinel feed, the chokepoint matrix and the producer matrix
opens a detail modal explaining **why** that score was assigned. Because risk
aggregates by `max` rather than by sum, exactly one event sets each score; the
modal names that driver, lists the other contenders, and shows the arithmetic
behind each contribution:

```text
0.588   severity 0.84  × 0.7 discount  · decayed over 26.2h
        "export routes cross Strait of Hormuz"
```

Chokepoint and producer modals also locate the subject on a small map, with the
halo scaled to its risk score.

---

## Design System

The UI runs on the MERIDIAN design tokens defined in `app/globals.css`, with a
persisted light/dark toggle in the header.

- **Tokens.** ~26 semantic tokens (`bg`, `panel`, `border`, `hair`, `fg`,
  `muted`, `accent`, `crit`, `safe`, `warn`, `orange` …) declared under
  `@theme inline`. The `inline` matters: with a plain `@theme`, Tailwind
  resolves the indirection in `:root` scope and the `.dark` overrides never
  take effect.
- **Soft fills are pre-mixed.** Use `bg-crit-soft`, never `bg-crit/15` — the
  alpha differs per theme and an opacity modifier washes out in light mode.
- **Theme switching** is a class on `<html>`, applied by an inline script in
  `<head>` before first paint so there is no flash. System preference is
  resolved into a real class rather than a `prefers-color-scheme` block, which
  keeps the CSS variables and the `dark:` variant from ever disagreeing.
- **Charts and Leaflet** take colours as props, not classes, so they read from
  `useChartTheme()` (`components/energy/chart-theme.ts`), which mirrors the CSS
  tokens as resolved hex. Keep the two in sync.

---

## The Shadow Cache Architecture

The fundamental design decision: **no external API call is ever made in the request path**.

```text
Traditional architecture:       Shadow Cache architecture:
User clicks button              User clicks button
    │                               │
    ▼                               ▼
Call GDELT API (2–10s)       Read from local Postgres (<5ms)
    │                               │
    ▼                               ▼
Call Gemini API (1–3s)       Read from local Neo4j (<10ms)
    │                               │
    ▼                               ▼
Call yfinance (1–3s)         Render result instantly
    │
    ▼
Render result (~15s total)
```

External APIs are queried **only in the cron_worker.py background process**, which writes results to the local databases. The dashboard reads exclusively from these local databases.

---

## Setup & Running

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | **3.11+** | Tested on 3.11 and 3.12 |
| Node.js | **18.17+** | Required by Next.js 14 |
| Docker + Docker Compose | **27+** | Recommended path — installs both databases for you |
| PostgreSQL | 14+ | Only needed if not using Docker |
| Neo4j Community | 5.x | Only needed if not using Docker |

---

### Option A — Docker (Recommended)

This is the fastest and most reliable path. Docker starts both databases, creates the schema, and loads all historical seed data automatically. No manual database setup required.

**Step 1 — Clone and configure credentials**

```bash
git clone <repo-url>
cd energy-supply-chain

# The .env file MUST exist before running docker-compose — Postgres reads
# POSTGRES_PASSWORD and NEO4J_PASSWORD from it at container creation time.
cd backend
copy .env.example .env        # Windows
# cp .env.example .env         # Mac/Linux
```

Open `backend/.env` and fill in at minimum:
- `DB_PASSWORD` — any password (must match what your app uses to connect)
- `NEO4J_PASSWORD` — any password
- `GEMINI_API_KEY` — free at https://aistudio.google.com/app/apikey (no credit card)
- `AISSTREAM_API_KEY` — free at https://aisstream.io

```bash
cd ..   # back to repo root
```

**Step 2 — Start both databases**

```bash
# From repo root (where docker-compose.yml lives)
docker-compose up -d

# Wait for both containers to be healthy (~15–30 seconds)
docker-compose ps
# postgres: healthy   neo4j: healthy
```

Postgres automatically runs `seed/schema.sql` then `seed/postgres_dump.sql` on first boot, loading all historical event data, backtest records, and market prices. **You do not need to run a separate restore script.**

> **What about Neo4j?** The Neo4j knowledge graph (chokepoints, export ports, refineries, crude grades and their relationships) is seeded by the Python application, not by Docker. It runs automatically the first time `uvicorn api:app` starts — before the first HTTP request arrives. If Neo4j is not yet seeded, the Reroute Matrix will return empty results; starting the backend fixes this immediately with no manual action.

**Step 3 — Install Python and Node dependencies**

```bash
# Backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
# source venv/bin/activate      # Mac/Linux
pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm install
cd ..
```

**Step 4 — Start the application (3 terminals)**

```bash
# Terminal 1 — FastAPI backend (also seeds Neo4j knowledge graph on first boot)
cd backend
uvicorn api:app --reload --port 8000

# Terminal 2 — Background cron worker (keeps data fresh every 60 min)
cd backend
python cron_worker.py

# Terminal 3 — React frontend
cd frontend
npm run dev
```

Open http://localhost:3000 — the dashboard should show populated charts immediately.

---

### Option B — Manual Database Setup (without Docker)

Use this path if you prefer to manage Postgres and Neo4j yourself.

**Postgres:**

```bash
# Create the database
psql -U postgres -c "CREATE DATABASE energy_resilience;"

# Restore schema and seed data (required — without this, dashboard is empty for hours)
# Windows:
.\scripts\restore_seed_data.ps1
# Mac/Linux:
bash scripts/restore_seed_data.sh
```

**Neo4j:**

1. Install Neo4j Community 5.x and start it
2. Open http://localhost:7474 in your browser
3. Log in with `neo4j` / `neo4j` (default credentials on first boot)
4. You will be prompted to set a new password — **use the same value as `NEO4J_PASSWORD` in `backend/.env`**
5. The knowledge graph seeds automatically when `uvicorn api:app` starts (no manual import step)

**Install and start:**

Follow Steps 1, 3, and 4 from Option A above (skip Step 2).

> **Important:** Without the seed restore step, the dashboard will appear empty — 0 risk events, no backtest charts, flat market data — until the background cron worker accumulates enough live data, which can take several hours. Always run the restore script.

---

## Environment Variables

All configuration lives in `backend/.env`. Copy `backend/.env.example` to `backend/.env` and fill in your values.

```bash
# ── PostgreSQL ────────────────────────────────────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME=energy_resilience
DB_USER=postgres
DB_PASSWORD=your_password        # Required — dashboard won't start without this

# ── Neo4j ─────────────────────────────────────────────────────────────────
NEO4J_URI=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password     # Required — Reroute Matrix won't work without this

# ── Gemini AI ──────────────────────────────────────────────────────────────
# Get free key instantly: https://aistudio.google.com/app/apikey (no credit card)
# Without this: Sentinel Agent disabled, War Room briefings show placeholder.
#               All historical data, charts, and deterministic models still work.
GEMINI_API_KEY=your_gemini_api_key

# Optional pool of extra keys (comma-separated). The free tier caps requests
# per key, so a 429/RESOURCE_EXHAUSTED rotates to the next key immediately
# rather than stalling scoring until the quota window resets.
GEMINI_API_KEYS=

# Note: gemini-2.5-flash returns 404 for API accounts created after Google
# restricted it, so a mixed-age key pool must standardise on an alias every
# key can call. One model across all keys also keeps severity calibrated.
GEMINI_MODEL=gemini-flash-latest

# ── News fallback providers (used when GDELT is rate-limited) ──────────────
# Tried freshest-first; daily usage is tracked in the provider_quota table so
# budgets survive a worker restart.
NEWSDATA_API_KEY=            # 200 req/day, real-time
GNEWS_API_KEY=               # 100 req/day, ~12h delay
NEWSAPI_API_KEY=             # 100 req/day, ~24h delay, non-commercial only
GDELT_TIMESPAN=12h           # Lookback per GDELT call

# ── AISStream.io ───────────────────────────────────────────────────────────
# Get free key instantly: https://aisstream.io
# Without this: Threat Map shows last-known vessel positions from seed data.
AISSTREAM_API_KEY=your_aisstream_key

# ── SDI Formula Weights (must sum exactly to 1.0) ─────────────────────────
SDI_W1=0.50    # Gemini geopolitical risk score
SDI_W2=0.25    # Vessel density anomaly (AIS)
SDI_W3=0.10    # Brent crude price deviation
SDI_W4=0.15    # Freight cost deviation (BOAT ETF)

# ── Cron Worker ────────────────────────────────────────────────────────────
CRON_INTERVAL_MINUTES=60     # Background refresh interval
AIS_SNAPSHOT_SECONDS=600     # How long to collect AIS data per cron cycle.
                             # Must exceed the ~360s AIS Type-5 broadcast
                             # period or most vessels are never type-classified.
```
