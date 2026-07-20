# Deployment Runbook — Free-Tier Hosting

Target architecture:

```
Browser
   │
   ├── Cloudflare Pages ............ Next.js frontend (static export)
   │        │ HTTPS
   │        ▼
   └── Cloudflare Tunnel ........... public entry, no inbound ports
            │
            ▼
        Oracle Cloud A1 VM .......... FastAPI + cron_worker  (stateless)
            │
            ├── Neon ................ PostgreSQL (pooled endpoint)
            └── Neo4j AuraDB Free ... knowledge graph
```

Everything sits inside free tiers. The VM holds no data, so it can be rebuilt
without loss.

---

## 0. Before you start

**Rotate every API key.** The keys currently in `backend/.env` (Gemini ×3,
AISStream, NewsData, GNews, NewsAPI) have been pasted into chat logs. Generate
fresh ones and put the new values only in the VM's `.env`, which is gitignored.

Verify nothing secret is tracked:

```bash
git ls-files | grep -E "\.env$"      # must return nothing
```

---

## 1. Code changes (do these first, locally)

Four changes. The first two are hard blockers; the last two prevent slow
problems later.

### 1.1 Batch the upserts — REQUIRED for remote Postgres

`backend/src/database/postgres_db.py` has four write paths that execute one
statement **per row** inside a Python loop:

| function | line (approx) |
|---|---|
| `upsert_news` | 277 |
| `upsert_vessel` | 384 |
| `upsert_vessel_types` | 538 |
| `upsert_price` | 582 |

`upsert_vessel` fires ~634 INSERTs per AIS snapshot. Against localhost that
costs 0.1s; against a managed database at 60 ms RTT it costs **38 seconds**.

SQLAlchemy's psycopg2 dialect already runs in `EXECUTEMANY_VALUES` mode, so
handing it the whole list rewrites the work into multi-row `VALUES` — roughly
2 round trips instead of 634.

Change each loop from this shape:

```python
inserted = 0
with get_conn() as conn:
    for rec in records:
        result = conn.execute(stmt, {"url": rec.get("url"), ...})
        inserted += result.rowcount
return inserted
```

to this:

```python
params = [{"url": rec.get("url"), ...} for rec in records]
with get_conn() as conn:
    result = conn.execute(stmt, params)
return result.rowcount or 0
```

`rowcount` stays correct with `ON CONFLICT DO NOTHING` — it reports only the
rows actually inserted, which is what these functions return. Verified against
Postgres: 5 new → 5; 1 duplicate + 1 new → 1.

Then run the suite — it covers these paths:

```bash
cd backend && venv/Scripts/python -m pytest -q      # expect 114 passed
```

### 1.2 Make CORS configurable — REQUIRED for a hosted frontend

`backend/api.py` currently hardcodes localhost:

```python
allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:5173"],
```

The browser calls the API directly (`lib/api.ts` uses `NEXT_PUBLIC_API_URL`),
so a Pages-hosted frontend will be blocked until this reads from the
environment:

```python
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Do **not** use `["*"]` — the API has no auth, so a wildcard lets any site drive
your Gemini quota.

### 1.3 Switch the frontend to static export

The app has no API routes and does all fetching client-side, so it exports as
a pure static site and needs no Cloudflare adapter.

In `frontend/next.config.mjs`:

```js
const nextConfig = {
  output: 'export',          // add this
  typescript: { ignoreBuildErrors: true },
  images: { unoptimized: true },
  reactStrictMode: false,
}
```

`next build` then emits `out/`. Confirm it works locally before deploying:

```bash
cd frontend && npm run build && ls out/index.html
```

### 1.4 Add data retention

`vessel_telemetry` grows ~23k rows/month with no cleanup, while the modeler
only ever reads the last **7 days** (`fetch_region_tanker_buckets`) and 24h for
live positions. Keep 14 days for margin.

Add to `postgres_db.py`:

```python
def purge_old_telemetry(days: int = 14) -> int:
    """Drop vessel rows past the analysis window (modeler reads 7 days)."""
    try:
        with get_conn() as conn:
            result = conn.execute(
                text("DELETE FROM vessel_telemetry "
                     "WHERE recorded_at < NOW() - make_interval(days => :days)"),
                {"days": days},
            )
            return result.rowcount or 0
    except Exception as exc:
        logger.error("purge_old_telemetry failed: %s", exc)
        return 0
```

and call it from a daily job in `cron_worker.py`:

```python
schedule.every(24).hours.do(_run_step_safely, "Retention", step_retention)
```

---

## 2. Provision the managed databases

### 2.1 Neon (PostgreSQL)

1. Create a project. **Pick the region closest to where your Oracle VM will
   live** — every round trip crosses this link.
2. Copy the **pooled** connection string (it contains `-pooler`). This matters:
   SQLAlchemy is configured `pool_size=5, max_overflow=10`, so it can open up
   to 15 connections — more than free-tier direct limits typically allow.
3. Load the schema. The app creates tables itself on boot via `init_schema()`,
   so you can either let it, or seed historical data first:

```bash
# optional: move your existing local data across
pg_dump -U postgres energy_resilience > dump.sql
psql "<neon-pooled-url>" < dump.sql
```

Neon suspends after a few minutes idle but resumes in well under a second, and
your worker touches it every 15 minutes, so it stays warm in practice.

### 2.2 Neo4j AuraDB Free

1. Create the one free instance (one per account).
2. Save the generated password — it is shown **once**.
3. Note the `neo4j+s://` URI.

No import needed: the graph is seeded from code by `seed_graph()`, which runs
on API startup. It is only 60 nodes / 84 relationships.

Aura Free pauses when idle. Your worker queries it every ~15 minutes via
`_get_producer_countries()`, so it stays awake while the worker runs — but if
the VM is down for several days, expect to resume it manually.

---

## 3. Oracle Cloud VM

### 3.1 Create the instance

- Shape: **VM.Standard.A1.Flex (Ampere ARM)**, **1 OCPU / 6 GB**.
  Do not take the full 2 OCPU / 12 GB: running that 24/7 consumes ~97% of the
  monthly 1,500 OCPU-hour and 9,000 GB-hour allowances, leaving no room to
  stand up a replacement alongside the old one.
- Image: Ubuntu LTS (ARM build).
- Boot volume: default is fine (200 GB total allowance).
- **You do not need to open any ingress ports** — Cloudflare Tunnel dials out.

> **Idle reclamation.** Oracle may reclaim an instance if, over 7 days, CPU
> *and* network *and* memory are all under 20%. With Postgres moved to Neon
> this VM will sit near ~365 MB, which is ~6% of 6 GB. Since the criteria are
> all-of, clearing any one protects you — the simplest lever is a smaller
> memory allocation (2–3 GB), which also stretches your monthly budget.

### 3.2 Install

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv git
git clone <your-repo> ~/energy-supply-chain
cd ~/energy-supply-chain/backend
python3.12 -m venv venv
./venv/bin/pip install -r requirements.txt
```

ARM note: `pandas`, `numpy` and `psycopg2-binary` all publish `aarch64`
wheels, and `searoute` needs only `geojson` + `networkx` (pure Python), so
this should install without compiling.

### 3.3 Configure

Create `backend/.env` on the VM with the **rotated** keys:

```ini
# Managed databases
DB_HOST=<neon-host>
DB_PORT=5432
DB_NAME=<neon-db>
DB_USER=<neon-user>
DB_PASSWORD=<neon-password>

NEO4J_URI=neo4j+s://<your-aura-id>.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<aura-password>

# Frontend origin — must match your Pages domain exactly
CORS_ORIGINS=https://<your-project>.pages.dev

# Rotated keys
GEMINI_API_KEY=...
GEMINI_API_KEYS=...,...
GEMINI_MODEL=gemini-flash-latest
AISSTREAM_API_KEY=...
NEWSDATA_API_KEY=...
GNEWS_API_KEY=...
NEWSAPI_API_KEY=...

# Tuning (see comments in .env.example before changing)
AIS_SNAPSHOT_SECONDS=600
CRON_INTERVAL_MINUTES=15
GDELT_TIMESPAN=12h
SDI_W1=0.50
SDI_W2=0.25
SDI_W3=0.10
SDI_W4=0.15
```

If your Neon setup needs SSL enforced, confirm how `postgres_db.py` builds its
URL and append `?sslmode=require` accordingly.

Smoke-test before daemonising:

```bash
cd ~/energy-supply-chain/backend
./venv/bin/python -c "from src.database.postgres_db import init_schema; init_schema()"
./venv/bin/python -c "from src.database.neo4j_graph import seed_graph; seed_graph()"
./venv/bin/uvicorn api:app --port 8000 &
curl -s localhost:8000/api/metrics/live | head -c 200
```

### 3.4 Run as services

`/etc/systemd/system/energy-api.service`:

```ini
[Unit]
Description=Energy Resilience API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/energy-supply-chain/backend
ExecStart=/home/ubuntu/energy-supply-chain/backend/venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/energy-worker.service`:

```ini
[Unit]
Description=Energy Resilience Cron Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/energy-supply-chain/backend
ExecStart=/home/ubuntu/energy-supply-chain/backend/venv/bin/python cron_worker.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now energy-api energy-worker
journalctl -u energy-worker -f
```

Bind the API to `127.0.0.1`, not `0.0.0.0` — the tunnel reaches it locally and
nothing else should.

The worker holds a 600-second AIS WebSocket every hour. That is fine on a real
VM and is precisely why this piece cannot be serverless.

---

## 4. Cloudflare Tunnel

```bash
# install cloudflared (ARM64 build), then:
cloudflared tunnel login
cloudflared tunnel create energy-api
cloudflared tunnel route dns energy-api api.<your-domain>
```

`~/.cloudflared/config.yml`:

```yaml
tunnel: <tunnel-uuid>
credentials-file: /home/ubuntu/.cloudflared/<tunnel-uuid>.json

ingress:
  - hostname: api.<your-domain>
    service: http://localhost:8000
  - service: http_status:404
```

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
curl -s https://api.<your-domain>/api/metrics/live | head -c 200
```

You need a domain on Cloudflare for a named tunnel. Quick tunnels give a
random `trycloudflare.com` URL that changes on restart — fine for a smoke test,
not for a deployment, since it would break `CORS_ORIGINS` and
`NEXT_PUBLIC_API_URL` on every restart.

---

## 5. Cloudflare Pages

1. Connect the repo.
2. Build settings:
   - Root directory: `frontend`
   - Build command: `npm run build`
   - Output directory: `out`
3. Environment variable:
   - `NEXT_PUBLIC_API_URL = https://api.<your-domain>`

This is baked in at **build** time, not read at runtime — changing it later
requires a rebuild, not just a redeploy.

Then set `CORS_ORIGINS` on the VM to the final Pages domain and restart the
API. Custom domain? Include both, comma-separated.

---

## 6. Verify

```bash
# API reachable through the tunnel
curl -s https://api.<your-domain>/api/metrics/live

# CORS accepts the real frontend origin
curl -s -I -X OPTIONS https://api.<your-domain>/api/metrics/live \
  -H "Origin: https://<your-project>.pages.dev" \
  -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin
```

In the browser, confirm:

- KPI header populates (proves Postgres + the API path)
- **Reroute Matrix → Generate** returns rows (proves Aura connectivity)
- Threat Map renders vessels (proves AIS ingestion has run)
- Risk Intelligence shows events (proves Gemini + news ingestion)

Then watch one full worker cycle:

```bash
journalctl -u energy-worker -f
```

You want to see `MARKET ✓`, a GDELT or fallback fetch, `sentinel_agent: batch
produced N event(s)`, and `SDI snapshot persisted`.

---

## 7. Ongoing

**Backups.** Neon handles Postgres. Aura Free does not back up — but the graph
is rebuilt from code by `seed_graph()`, so there is nothing to lose.

**Health.** Both managed services pause when idle. They stay warm off the
worker's own traffic, so the meaningful alert is *"has the worker run
recently?"* — check that `sdi_snapshots` has a row from the last hour.

**Quota.** The three news providers are capped per day and tracked in the
`provider_quota` table:

```sql
SELECT * FROM provider_quota WHERE usage_date = CURRENT_DATE;
```

**Known slow path.** A Reroute Matrix generate takes ~6.5s, almost entirely in
`searoute`'s nautical distance calculation — not the database, and not
something hosting will change. Caching port→refinery distances would fix it;
they are fixed geography.
