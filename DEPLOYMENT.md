# Deployment Runbook — Free-Tier Hosting

```
Browser
   │
   ├── Cloudflare Pages ............ Next.js frontend (static export)
   │        │ HTTPS
   │        ▼
   └── Render Web Service .......... FastAPI (read-only API)
            │
            ├── Neon ................ PostgreSQL (pooled endpoint)
            └── Neo4j AuraDB Free ... knowledge graph

GitHub Actions (ingest.yml, hourly) ── writes ──► Neon / AuraDB
```

Live: <https://energy-supply-chain.pages.dev> · API:
`https://energy-supply-chain-backend.onrender.com`

The API holds no state of its own, so it can be rebuilt without loss.

---

## 0. Before you start

**Rotate any key that has ever been pasted into a chat, issue or log.** Put
the new values only into the platform settings (Render, GitHub secrets),
never into a committed file.

```bash
git ls-files | grep -E "\.env$"      # must return nothing
```

---

## 1. The free-tier constraints that shaped this

Read this before changing intervals — the defaults are not arbitrary.

**Render** gives 750 instance-hours per month. Free services sleep after 15
minutes without inbound traffic, and an in-process worker sleeps with them.
That is why ingestion now runs on GitHub Actions: data stays fresh whether or
not anyone is visiting, and the API only needs to be awake to serve requests.

**Neon** bills compute-hours, not queries, and needs ~5 idle minutes to scale
to zero, so *frequency* costs far more than *duration*:

- Ingestion runs hourly (`17 * * * *`), not every 15 minutes.
- `/healthz` touches **no database**. Point uptime pingers at it and nothing
  else; pinging a data endpoint would hold Neon awake permanently.
- Backtests are dispatched in-process rather than through a polled queue.

**Check your Neon compute size.** CU-hours = compute units × hours, so 100
CU-hours buys 400 h at 0.25 CU but 100 h at 1 CU. The AIS window holds the
database awake for ~10 minutes per run; at 1 CU consider running AIS less
often.

**Memory.** The stack is ~190 MB resident. On a 512 MB instance that leaves
room for request handling and one backtest, hence `BACKTEST_MAX_CONCURRENT=1`.

---

## 2. Provision the managed databases

### 2.1 Neon (PostgreSQL)

1. Create a project in the region closest to Render.
2. Copy the **pooled** connection string (contains `-pooler`): SQLAlchemy can
   open up to 15 connections, more than direct free-tier limits allow.
3. Tables are created on boot by `init_schema()` (idempotent, including
   `ADD COLUMN IF NOT EXISTS` migrations). To carry history across:

```bash
pg_dump -U postgres energy_resilience > dump.sql
psql "<neon-pooled-url>" < dump.sql
```

### 2.2 Neo4j AuraDB Free

1. Create the free instance (one per account) and save the password — it is
   shown **once**.
2. Note the `neo4j+s://<id>.databases.neo4j.io` URI.

No import needed: `seed_graph()` seeds it from code on startup (~60 nodes).

**Aura Free pauses after a few days without activity and is deleted if left
paused.** The hourly ingestion job touches the graph, which keeps it active.
If the logs show `Failed to DNS resolve address <id>.databases.neo4j.io`, the
instance is gone: create a new one and update `NEO4J_URI` / `NEO4J_PASSWORD`
in Render **and** in the GitHub secrets. Until then the API serves the graph
from seed data, so the Reroute page keeps working.

---

## 3. Render (API)

### 3.1 Create the service

New → **Web Service** → connect the repo.

| setting | value |
|---|---|
| Root directory | `backend` |
| Runtime | Docker (`backend/Dockerfile`) |
| Instance type | Free |
| Health check path | `/healthz` |
| Auto-Deploy | **After CI checks pass** |

The image binds `$PORT`, runs as a non-root user and healthchecks `/healthz`.

### 3.2 Environment variables

`load_dotenv()` does not override variables set by the platform, and
`.dockerignore` keeps `.env` out of the image, so Render's settings are
authoritative.

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

# Ingestion runs on GitHub Actions (§4). Keep this 0 once that is green;
# set 1 only if you want the API to run the scheduler itself instead.
RUN_WORKER=0

# CORS — exact production origin, plus a regex for Cloudflare previews
CORS_ORIGINS=https://energy-supply-chain.pages.dev
CORS_ORIGIN_REGEX=^https://([a-z0-9-]+\.)?energy-supply-chain\.pages\.dev$

# Gemini (War Room brief; Sentinel runs in the ingestion job)
GEMINI_API_KEY=...
GEMINI_API_KEYS=...           # optional comma-separated pool
GEMINI_MODEL=gemini-flash-latest
GEMINI_FALLBACK_MODEL=gemini-flash-lite-latest

BACKTEST_MAX_CONCURRENT=1
LOG_TO_FILE=0

# Which proxy header identifies the client for rate limits. "cloudflare"
# (default) trusts CF-Connecting-IP, which Cloudflare sets and refuses from
# clients; "none" uses the TCP peer. X-Forwarded-For is never trusted.
TRUSTED_PROXY=cloudflare
```

**One instance, one uvicorn worker.** Rate limits and the War Room cache are
in-process memory; a second instance would have its own. The Dockerfile's
`CMD` is single-worker; do not add `--workers`.

### 3.3 First boot

The port binds in under a second; schema setup and the Neo4j seed run behind
it. Expect these log lines:

```
CORS allowed origins: ['https://energy-supply-chain.pages.dev'] (regex: ^https://...)
Database schema verified.
Neo4j knowledge graph verified.
```

---

## 4. Ingestion (GitHub Actions)

`.github/workflows/ingest.yml` runs `python cron_worker.py --once --with ais`
every hour at :17, adding `portwatch,retention` at 00:xx and 12:xx UTC. It can
also be started by hand: Actions → **ingest** → Run workflow.

Add **repository secrets** (Settings → Secrets and variables → Actions) with
the same values as Render:

`DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD GEMINI_API_KEYS AISSTREAM_API_KEY
NEWSDATA_API_KEY GNEWS_API_KEY NEWSAPI_API_KEY NEO4J_URI NEO4J_USER NEO4J_PASSWORD`

Optional repository **variable** `GEMINI_MODEL`. Until `DB_HOST` exists the
job skips itself with a notice instead of failing.

Then set `RUN_WORKER=0` on Render so the pipeline does not run twice.

> Scheduled workflows on a public repo are paused by GitHub after 60 days
> without repository activity. Re-enable from the Actions tab if that happens.

---

## 5. Keep the API awake (optional)

Render sleeps after 15 idle minutes; the first request after that takes
~30–60 s. Frontend requests time out at 60 s, which covers a cold start. To
avoid it entirely, add an uptime monitor on
`https://<service>.onrender.com/healthz` every 10 minutes — **only `/healthz`**,
for the Neon reason in §1.

---

## 6. Cloudflare Pages (frontend)

| setting | value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm run build` |
| Output directory | `out` |
| Production branch | `main` |

Variables are compiled into the bundle at build time, so **set them for both
Production and Preview, then rebuild**:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://energy-supply-chain-backend.onrender.com` |
| `NEXT_PUBLIC_CARTO_KEY` | your CARTO key (optional; Esri tiles otherwise) |

A production build (`CF_PAGES_BRANCH=main`) **fails on purpose** if
`NEXT_PUBLIC_API_URL` is missing or points at localhost. Preview builds are not
blocked, but without the variable they ship a site that cannot reach the API.

`frontend/public/_headers` sets the CSP, HSTS, `X-Frame-Options: DENY` and a
Permissions-Policy. Its `connect-src` names the Render URL, so update it if the
API moves.

---

## 7. Verify

```bash
B=https://energy-supply-chain-backend.onrender.com

curl -s $B/healthz                                   # {"status":"ok"}
curl -s $B/api/metrics/live | head -c 300            # Neon + data reachable
curl -s -o /dev/null -w "%{http_code}\n" "$B/api/risk/events?limit=500"   # 422 = current code deployed

curl -sI -H "Origin: https://energy-supply-chain.pages.dev" $B/api/metrics/live \
  | grep -i access-control-allow-origin             # echoes the origin, never "*"

curl -sI https://energy-supply-chain.pages.dev/ | grep -i content-security-policy
```

In the dashboard, open devtools → Network and confirm requests go to
`onrender.com`, and that the data-health panel shows each feed's state.

---

## 8. Ongoing

- **Budgets:** Render instance-hours and Neon compute-hours fail silently —
  check both consoles monthly.
- **Stalls:** a step running past `SLOW_STEP_WARN_SECONDS` (900) logs
  `possible stall`; repeated warnings mean an upstream API is hanging.
- **Backtests** run in daemon threads and do not survive a restart; anything
  mid-flight is marked failed on next boot. A second concurrent backtest
  returns 503.
- **AIS 429s** in the ingestion logs are retried automatically; persistent
  ones mean AISStream is throttling that IP.

---

## Appendix: running locally

```bash
cd backend && uvicorn api:app --reload      # API (RUN_WORKER defaults to 0)
cd backend && python cron_worker.py         # scheduler, optional
cd frontend && npm run dev                  # UI on :3000
```

If you set `RUN_WORKER=1` while `cron_worker.py` is running, the API sees the
existing worker through a cross-process lock and defers to it.
