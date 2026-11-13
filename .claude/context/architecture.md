# Architecture

```
Browser ── Cloudflare Pages (frontend/, Next.js static export → out/)
   │ fetch (NEXT_PUBLIC_API_URL)
   ▼
Render ── FastAPI backend/api.py  (+ in-process cron worker when RUN_WORKER=1)
   ├── Neon Postgres   (news, events, prices, vessels, SDI snapshots, backtests)
   └── Neo4j           (knowledge graph: ports, grades, chokepoints, refineries)
External: Gemini (scoring + briefs), GDELT → NewsData → GNews → NewsAPI
(fallback chain), yfinance (BZ=F, NG=F, USO, XLE, BOAT), AISStream websocket,
IMF PortWatch, CARTO/Esri map tiles.
```

## Backend (`backend/`)

| Path | Role |
|---|---|
| `api.py` | All REST routes, CORS, rate limits, error mapping (503 on DB down) |
| `cron_worker.py` | Scheduled pipeline: market → freight → GDELT → Sentinel → SDI snapshot; AIS + PortWatch on own timers; file lock |
| `backtest_dispatch.py`, `run_backtest.py` | In-process threaded backtests (max 1 concurrent) |
| `src/agents/sentinel_agent.py` | Gemini scoring of headlines → list of events; key pool rotation; headline sanitising; RPM guard |
| `src/agents/modeler_agent.py` | SDI, chokepoint/producer matrices, score explanations, AIS self-calibrated density |
| `src/agents/fixer_agent.py` | Reroute matrix (Neo4j + searoute), landed cost, resilience score |
| `src/agents/spr_agent.py` | India SPR burn-down + demand levers + macro impact |
| `src/agents/briefing_agent.py` | Gemini War Room brief |
| `src/database/postgres_db.py` | SQLAlchemy pool, `init_schema()` (idempotent), all SQL; read helpers raise `DatabaseUnavailable` |
| `src/database/neo4j_graph.py` | Driver w/ reconnect cooldown, `seed_graph()` (MERGE-only) |
| `src/ingestion/*` | gdelt_collector (3-way query rotation), news_providers (fallbacks + daily quota table), market/freight trawlers, ais_streamer, portwatch |
| `src/utils/` | constants (aliases, SDI bands), metrics (weights), schemas (bounded pydantic), rate_limit |
| `tests/` | ~140 pytest tests; conftest wraps each test in a rolled-back transaction |

Endpoints: `/healthz` (no DB), `/api/metrics/live`, `/api/risk/{events,events/{id},chokepoints[/{name}],producers[/{name}],sdi-timeline}`,
`/api/market/{prices,vessels}`, `/api/config/{chokepoints,refineries,grades}`,
`POST /api/orchestrator/{reroute,spr,war-room}`, `/api/backtest/{jobs,trigger,{event}}`.

## Frontend (`frontend/`)

- `app/` — layout (fonts, pre-paint theme script), `globals.css` (all colours
  are `--x-<darkhex>` CSS vars; `html.light` swaps values).
- `components/m/shell.tsx` — hash router (`#overview|map|risk|market|reroute|spr|war|history`),
  desktop sidebar ≥lg, mobile 5-tab bar (Overview·Map·Risk·Markets·Respond) + sub-switches.
- `components/m/data.tsx` — one shared fetch cycle (30 s, pauses when tab hidden),
  filters, `feedHealth()`, SDI `components()`.
- `components/m/pages/*` — one file per page. `detail.tsx` — drill-down drawer.
- `lib/api.ts` — typed fetchers (shared with legacy).
- `public/_headers` — CSP + security headers for Cloudflare Pages.
- `tests/smoke.spec.ts` — Playwright vs `out/`, API pointed at a closed port.

Design source: Claude Design canvases, copies in `docs/design/meridian-v1|v2/`.
