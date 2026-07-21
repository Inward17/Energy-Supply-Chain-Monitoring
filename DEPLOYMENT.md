# Deployment Runbook — Free-Tier Hosting

Target architecture:

```
Browser
   │
   ├── Cloudflare Pages ............ Next.js frontend (static export)   [LIVE]
   │        │ HTTPS
   │        ▼
   └── Render Web Service .......... FastAPI + in-process cron worker
            │
            ├── Neon ................ PostgreSQL (pooled endpoint)
            └── Neo4j AuraDB Free ... knowledge graph
```

The service holds no data, so it can be rebuilt without loss.

**Frontend is already deployed:** <https://energy-supply-chain.pages.dev/>
It renders but shows no data until the backend below exists.

---

## 0. Before you start

**Rotate every API key.** The keys currently in `backend/.env` (Gemini ×3,
AISStream, NewsData, GNews, NewsAPI) have been pasted into chat logs. Generate
fresh ones and put the new values only into Render's environment settings.

Verify nothing secret is tracked:

```bash
git ls-files | grep -E "\.env$"      # must return nothing
```

---

## 1. The free-tier constraints that shaped this

Read this before changing intervals — the defaults are not arbitrary.

**Render** gives 750 instance-hours per month per workspace. A 31-day month is
744 hours, so keeping one service awake around the clock leaves ~6 hours of
headroom and **only works if you run no other free service on the account**.
Free services also sleep after 15 minutes of inactivity, so an external pinger
is required to stay up.

**Neon** bills compute-hours, not queries, and cannot scale to zero until
~5 idle minutes have passed. Every wake-up therefore costs a 5-minute minimum
regardless of how little work you did. This makes *frequency* far more
expensive than *duration*, which is why:

- `CRON_INTERVAL_MINUTES` defaults to **60**, not 15. At 15-minute ticks the
  database is awake roughly 37% of the month; at 60 it is under 10%.
- `/healthz` touches **no database**. Point your uptime pinger at it and
  nothing else. Pinging a data endpoint every 5 minutes would hold Neon open
  permanently and drain the allowance with no users at all.
- Backtests are dispatched in-process instead of through a polled queue. The
  old 30-second poll ran a query twice a minute forever, which alone was
  enough to stop Neon ever going idle.

**Check your Neon compute size before trusting the estimates.** CU-hours are
compute-units × wall-clock-hours, so a 100 CU-hour allowance buys 400 hours at
0.25 CU but only 100 hours at 1 CU. If yours is 1 CU, raise
`AIS_INTERVAL_MINUTES` to `180` — the AIS window is the single most expensive
recurring job because it holds the database awake across a 10-minute
collection.

**Memory.** The dependency stack measures ~190 MB resident once loaded
(pandas 67 MB, then fastapi/neo4j/sqlalchemy/yfinance/searoute incrementally).
On a 512 MB instance that leaves room for request handling and exactly one
backtest, which is why `BACKTEST_MAX_CONCURRENT` defaults to 1.

---

## 2. Provision the managed databases

### 2.1 Neon (PostgreSQL)

1. Create a project. **Pick the region closest to your Render region** — every
   round trip crosses this link.
2. Copy the **pooled** connection string (it contains `-pooler`). This matters:
   SQLAlchemy is configured `pool_size=5, max_overflow=10`, so it can open up
   to 15 connections — more than free-tier direct limits typically allow.
3. Note the **compute size** (see §1). It decides your real budget.
4. Load the schema. The app creates tables itself on boot via `init_schema()`,
   so you can either let it, or seed historical data first:

```bash
# optional: move your existing local data across
pg_dump -U postgres energy_resilience > dump.sql
psql "<neon-pooled-url>" < dump.sql
```

### 2.2 Neo4j AuraDB Free

1. Create the one free instance (one per account).
2. Save the generated password — it is shown **once**.
3. Note the `neo4j+s://` URI.

No import needed: the graph is seeded from code by `seed_graph()`, which runs
on startup. It is only 60 nodes / 84 relationships.

Aura Free pauses when idle. The worker queries it each cycle, so it stays
awake while the service runs — but after several days down, expect to resume
it manually from the console.

---

## 3. Render

### 3.1 Create the service

New → **Web Service** → connect the GitHub repo.

| setting | value |
|---|---|
| Root directory | `backend` |
| Runtime | Docker |
| Instance type | Free |
| Health check path | `/healthz` |

The repo's `backend/Dockerfile` is used as-is. It already binds `$PORT`, runs
as a non-root user, and healthchecks `/healthz`.

### 3.2 Environment variables

Set these in the Render dashboard. Do **not** commit a `.env` — `load_dotenv`
runs with `override=True`, so a `.env` inside the image would silently win
over everything set here. `.dockerignore` excludes it for that reason.

```bash
# Databases
DB_HOST=<neon-pooled-host>
DB_PORT=5432
DB_NAME=<neon-db>
DB_USER=<neon-user>
DB_PASSWORD=<neon-password>
DB_SSLMODE=require            # Neon refuses plaintext

NEO4J_URI=neo4j+s://<id>.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<aura-password>

# Run the pipeline inside this process — Render's free tier covers a web
# service but bills a separate background worker.
RUN_WORKER=1

# Frontend origin — must match exactly, no trailing slash
CORS_ORIGINS=https://energy-supply-chain.pages.dev

# Rotated keys (see §0)
GEMINI_API_KEY=...
GEMINI_API_KEYS=...           # comma-separated pool, optional
AISSTREAM_API_KEY=...
NEWSDATA_API_KEY=...
GNEWS_API_KEY=...
NEWSAPI_API_KEY=...

# Tuning — see §1 before changing
CRON_INTERVAL_MINUTES=60
AIS_INTERVAL_MINUTES=60       # raise to 180 if Neon compute is 1 CU
BACKTEST_MAX_CONCURRENT=1
LOG_TO_FILE=0
```

**Keep the service at one instance and one uvicorn worker.** Two would each
start their own scheduler, doubling every job and every metered Gemini call.
The Dockerfile's default `CMD` is already single-worker; do not add
`--workers`.

### 3.3 First boot

The port binds in well under a second; schema setup, the Neo4j seed and the
first ingestion cycle run behind it (measured at 0.6s to first response with
both databases unreachable). Expect the dashboard to stay empty for a few
minutes after deploy while that first cycle completes.

---

## 4. Keep it awake

Render sleeps a free service after 15 minutes idle. Add an uptime monitor:

- URL: `https://<your-service>.onrender.com/healthz`
- Interval: 10 minutes

**It must be `/healthz`.** Any other route queries Postgres and would keep
Neon awake permanently — see §1.

---

## 5. Point the frontend at it

`NEXT_PUBLIC_API_URL` is compiled into the bundle at build time, so setting it
is not enough — you must rebuild.

1. Cloudflare Pages → your project → Settings → **Variables and secrets**
2. Add `NEXT_PUBLIC_API_URL = https://<your-service>.onrender.com`
3. Deployments → **Retry deployment** (or push a commit)

Miss the rebuild and the deployed bundle keeps its `http://localhost:8000`
fallback.

---

## 6. Verify

```bash
# 1. Health — must answer instantly, even during startup
curl -s https://<service>.onrender.com/healthz
# {"status":"ok"}

# 2. Data layer — the real check that Neon and Aura are reachable
curl -s https://<service>.onrender.com/api/metrics/live | head -c 300

# 3. CORS — must echo the Pages origin, not "*"
curl -sI -H "Origin: https://energy-supply-chain.pages.dev" \
     https://<service>.onrender.com/api/metrics/live \
     | grep -i access-control-allow-origin

# 4. Frontend calls the right host
#    Load the dashboard, open devtools → Network, confirm requests go to
#    onrender.com and not localhost.
```

In Render's logs after a successful boot you should see:

```
CORS allowed origins: ['https://energy-supply-chain.pages.dev']
Database schema verified.
Neo4j knowledge graph verified.
RUN_WORKER=1 — running an initial ingestion cycle ...
Scheduling — cycle every 60m, AIS every 60m, PortWatch 12h, retention 24h.
In-process cron scheduler started.
```

---

## 7. Ongoing

**Watch the two budgets.** Render instance-hours and Neon compute-hours are
the limits you will hit first, and neither fails loudly — the service simply
stops. Check both consoles monthly.

**Watch for stall warnings.** A step running past `SLOW_STEP_WARN_SECONDS`
(default 900) logs `possible stall`. Steps run in separate threads, so one
stalling no longer blocks the others, but a repeated warning means an upstream
API is hanging.

**Backtests do not survive a restart.** They run in daemon threads; anything
mid-flight when the instance sleeps or redeploys is reaped and marked failed
on next boot. That is expected on a tier that idles out, not a bug.

**A second concurrent backtest returns 503.** The cap exists because two at
once will not fit in 512 MB. Raise `BACKTEST_MAX_CONCURRENT` only on a larger
instance.

---

## Appendix: running locally

Unchanged — two processes, as before:

```bash
# Terminal 1
cd backend && python cron_worker.py

# Terminal 2
cd backend && uvicorn api:app --reload

# Terminal 3
cd frontend && npm run dev
```

`RUN_WORKER` defaults to `0`, so the API does not schedule anything locally.
If you do set it while `cron_worker.py` is running, the API detects the
existing worker through a cross-process lock and defers to it rather than
double-running the pipeline.
