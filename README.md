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
│  └── price_history                        ├── CrudeGrade nodes      │
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

Every external API is hit **only in the background** (cron_worker.py). The Streamlit UI **never blocks on a live API call**. This means:
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
| News Data | GDELT Doc 2.0 API | Global event news headlines (free, no auth) |
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
The engine that keeps the Shadow Cache fresh. Runs in a separate terminal alongside `streamlit run app.py`.

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
- **Deduplication**: inserts only new URLs using `ON CONFLICT DO NOTHING`
- **Rate limiting**: GDELT throttles to ~1 req/sec; tenacity retries on 429 errors
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

- Collects for `AIS_SNAPSHOT_SECONDS` (default 120s) then disconnects cleanly
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
2. Builds a structured JSON prompt requesting: `region`, `disruption_type`, `severity (0-1)`, `affected_chokepoints`, `confidence`, `summary`
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
SDI = w1·P_risk + w2·ΔD_vessel + w3·ΔP_price

Where:
  P_risk   = Gemini Sentinel severity score (0–1)
  ΔD_vessel = AIS vessel count deviation from baseline (0–1)
  ΔP_price  = Brent price z-score vs 30-day mean (0–1)
  w1=0.50, w2=0.30, w3=0.20  (overridable via SDI_W1/W2/W3 env vars)
```

- `compute_current_sdi()` — real-time global risk snapshot for the dashboard header
- `compute_chokepoint_risk_matrix()` — per-chokepoint breakdown with vessel counts and price impact
- `score_alternatives()` — resilience scoring for a set of rerouted alternatives

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

Designed to be rendered directly in the War Room tab using `st.info()`.

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

Weights (`w1`, `w2`, `w3`) are overridable via `SDI_W1`, `SDI_W2`, `SDI_W3` environment variables.

---

## Dashboard Tabs

| # | Tab | Description |
|---|---|---|
| 1 | 🌍 **Threat Map** | PyDeck globe displaying live vessel positions and a chokepoint risk heatmap |
| 2 | 🔴 **Risk Intelligence** | Gemini-scored event feed with SDI timeline chart |
| 3 | 📈 **Market Pulse** | Brent/NG/XLE candlestick charts + price impact KPI cards |
| 4 | 🔀 **Reroute Matrix** | Interactive 5-step procurement analysis — select a blocked chokepoint and destination refinery to get a ranked table of alternative crude sources |
| 5 | 🛢️ **SPR Optimizer** | SPR burn-down simulator with Plotly chart, demand management playbook, and GDP/inflation impact |
| 6 | ⚔️ **War Room** | One-click crisis scenario simulator — selects a scenario, runs the full pipeline, and generates an AI-written Executive Action Plan |

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
- Python 3.11+
- PostgreSQL 14+ (running locally)
- Neo4j Community Edition 5.x (running locally)
- AISStream.io account (free tier works)
- Google Gemini API key (free tier available)

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd energy-supply-chain

# 1. Setup Backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
copy .env.example .env
# Edit .env with your credentials

# 2. Setup Frontend
cd ../frontend
npm install
```

### First Run

```bash
# Terminal 1: Initialise databases and background cron loop
cd backend
python cron_worker.py --once
python cron_worker.py

# Terminal 2: Start the FastAPI API Bridge
cd backend
uvicorn api:app --reload --port 8000

# Terminal 3: Start the React frontend
cd frontend
npm run dev
```

---

## Environment Variables

All configuration is stored in `.env`. No credentials are hardcoded.

```env
# ── Database ───────────────────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=energy_resilience

# ── Neo4j ──────────────────────────────────────────────
NEO4J_URI=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# ── External APIs ──────────────────────────────────────
GEMINI_API_KEY=your_gemini_api_key
AISSTREAM_API_KEY=your_aisstream_key

# ── Tuning Knobs (optional) ────────────────────────────
CRON_INTERVAL_MINUTES=60       # How often the shadow cache refreshes
AIS_SNAPSHOT_SECONDS=120       # How long to collect AIS data per cycle
GEMINI_MODEL=gemini-2.5-flash  # Swap model without code changes

# ── SDI Weights (must sum to 1.0) ─────────────────────
SDI_W1=0.40   # Geopolitical risk score weight
SDI_W2=0.25   # Vessel density divergence weight
SDI_W3=0.15   # Price delta weight
SDI_W4=0.20   # Freight/Insurance stress weight
```
