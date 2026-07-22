"""
api.py
───────
FastAPI backend bridge for the Energy Supply Chain Resilience OS.

Replaces the Streamlit app.py as the serving layer. All Python agent logic
(fixer, spr, sentinel, briefing) is exposed as REST endpoints that the
React frontend can call via fetch().

Run with:
    uvicorn api:app --reload --port 8000

Terminals:
    Terminal 1: python cron_worker.py        (keeps DB fresh)
    Terminal 2: uvicorn api:app --reload     (this file)
    Terminal 3: cd energy-resilience-ui && npm run dev
"""

from __future__ import annotations

import json
import logging
import os
import threading
import pandas as pd
from typing import Any
from datetime import datetime, timedelta, date, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.utils.schemas import RerouteRequest, SprRequest, WarRoomRequest, BacktestRequest

# ── Agent imports (untouched business logic) ────────────────────────────────
from src.agents.fixer_agent import (
    find_alternatives,
    get_chokepoint_list,
    get_crude_grade_list,
    get_refinery_list,
)
from src.agents.spr_agent import calculate_spr_impact
from src.agents.briefing_agent import generate_emergency_brief
from src.agents.modeler_agent import (
    compute_current_sdi,
    compute_chokepoint_risk_matrix,
    compute_producer_country_risk_matrix,
    explain_chokepoint_risk,
    explain_producer_risk,
)
from src.database.postgres_db import (
    init_schema,
    fetch_unprocessed_news,
    fetch_vessels,
    fetch_latest_prices,
    fetch_risk_events,
    fetch_risk_event,
    fetch_latest_sdi,
    fetch_sdi_snapshots,
    upsert_sdi_snapshot,
    fetch_risk_events_backtest,
    create_backtest_job,
    update_backtest_job,
    fetch_all_backtest_jobs
)
from backtest_dispatch import dispatch as dispatch_backtest
from src.database.neo4j_graph import get_driver
from src.utils.constants import (
    COUNTRY_ALIASES,
    PRODUCER_TO_CHOKEPOINTS,
    canonical_country_name,
)

from dotenv import load_dotenv
load_dotenv(override=True)
from src.ingestion.market_trawler import get_brent_rolling_stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# ── FastAPI setup ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Energy Resilience OS API",
    description="REST bridge between the React frontend and the Python agent layer.",
    version="1.0.0",
)

# The dashboard calls this API straight from the browser, so the deployed
# frontend's origin has to be allowed explicitly. Set CORS_ORIGINS to a
# comma-separated list (e.g. "https://foo.pages.dev,https://dash.example.com").
# Defaults cover local development.
#
# Deliberately not "*": these endpoints are unauthenticated and spend metered
# third-party quota (Gemini, news providers), so a wildcard would let any site
# drive that spend.
_DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://localhost:3001,http://localhost:5173"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("CORS allowed origins: %s", CORS_ORIGINS)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe. Deliberately touches no database.

    A host that idles a service out after a few minutes has to be kept awake
    by an external pinger, which means this route is hit continuously forever.
    Pointing that at anything which queries Postgres would hold a serverless
    database open around the clock and drain a metered compute allowance
    without a single user visiting. Answering from memory costs nothing.

    Use /api/metrics/live instead to check that the data layer is reachable.
    """
    return {"status": "ok"}


# ── Startup ───────────────────────────────────────────────────────────────────

# Run the ingestion pipeline inside this process rather than as a separate
# service. Needed where a free tier covers a web service but bills a
# standalone worker; leave unset for the two-process local setup.
RUN_WORKER = os.getenv("RUN_WORKER", "0") == "1"


def _reap_orphaned_backtests() -> None:
    """Fail jobs that a restart left mid-flight.

    Backtests run in daemon threads, so anything still `running` when the
    process stopped is gone. On a host that spins the instance down when idle
    that is routine rather than exceptional, and without this the dashboard
    shows a job stuck at "running" that will never finish or fail.
    """
    try:
        for job in fetch_all_backtest_jobs():
            if job.get("status") in ("running", "pending"):
                update_backtest_job(
                    job["id"], "failed", "Interrupted by a server restart."
                )
                logger.info("Reaped orphaned backtest job %s.", job["id"])
    except Exception as exc:
        logger.warning("Could not reap orphaned backtest jobs: %s", exc)


def _deferred_startup() -> None:
    """Schema check, graph seed, first SDI snapshot, and optionally the worker.

    Runs off the startup path on purpose. A platform's deploy health check
    waits for the port to bind, and this work — a Neo4j seed, an SDI
    computation, then a full ingestion cycle including news fetch and Gemini
    scoring — takes minutes. Doing it inline means the deploy is marked failed
    before the app ever accepts a connection.
    """
    try:
        init_schema()
        logger.info("Database schema verified.")
    except Exception as exc:
        logger.warning("Could not verify DB schema: %s", exc)

    try:
        from src.database.neo4j_graph import seed_graph
        seed_graph()
        logger.info("Neo4j knowledge graph verified.")
    except Exception as exc:
        logger.warning("Neo4j seed failed (non-fatal): %s", exc)

    _reap_orphaned_backtests()

    try:
        upsert_sdi_snapshot(compute_current_sdi())
        logger.info("Initial SDI snapshot persisted.")
    except Exception as exc:
        logger.warning("Initial SDI snapshot failed: %s", exc)

    if not RUN_WORKER:
        return

    try:
        import cron_worker

        # One cycle now, because the scheduler's first tick is an interval
        # away and a cold instance would otherwise serve hour-old data.
        logger.info("RUN_WORKER=1 — running an initial ingestion cycle ...")
        cron_worker.run_cycle()

        # AIS and PortWatch are not part of a cycle — they are separate jobs on
        # 60-minute and 12-hour timers. Without this the timers restart on every
        # redeploy, so on a host that restarts for each config change they can
        # go indefinitely without firing. That is exactly what happened: news,
        # market and SDI kept updating while vessel telemetry stayed a day old.
        # Runs before the scheduler so its own AIS job cannot overlap this one.
        cron_worker.run_startup_steps()

        cron_worker.start_background_scheduler()
    except Exception as exc:
        logger.error("In-process worker failed to start: %s", exc, exc_info=True)


@app.on_event("startup")
def startup():
    """Bind the port immediately; do the slow work behind it."""
    threading.Thread(
        target=_deferred_startup, name="deferred-startup", daemon=True
    ).start()


# ── Endpoints: Metrics & Live Data ────────────────────────────────────────────

@app.get("/api/metrics/live")
def get_live_metrics() -> dict[str, Any]:
    """
    Return the current global Supply Disruption Index snapshot.
    Powers the KPI header bar across all dashboard tabs.
    """
    try:
        sdi_data = compute_current_sdi()
        return {
            "sdi_score":        sdi_data["sdi_score"],
            "sdi_band":         sdi_data.get("sdi_band", "LOW"),
            "confidence_low":   sdi_data["confidence_low"],
            "confidence_high":  sdi_data["confidence_high"],
            "p_risk":           sdi_data["p_risk"],
            "delta_d":          sdi_data["delta_d"],
            "delta_p":          sdi_data["delta_p"],
            "delta_f":          sdi_data["delta_f"],
            "current_brent":    sdi_data["current_brent"],
            "current_freight":  sdi_data["current_freight"],
            "price_impact_usd": sdi_data["price_impact_usd"],
            "top_region":       sdi_data["top_region"],
            "top_chokepoints":  sdi_data["top_chokepoints"],
            "vessel_count":     sdi_data["vessel_count"],
            "active_alerts":    sdi_data["active_alerts"],
            "gemini_configured": sdi_data.get("gemini_configured", True),
            "ais_configured":    sdi_data.get("ais_configured", True),
            "w1":               sdi_data.get("w1", 0.40),
            "w2":               sdi_data.get("w2", 0.25),
            "w3":               sdi_data.get("w3", 0.15),
            "w4":               sdi_data.get("w4", 0.20),
            "confidence":       sdi_data.get("confidence", 0.5),
            "ais_status":       sdi_data.get("ais_status", "unavailable"),
            "ais_type_coverage": sdi_data.get("ais_type_coverage", 0.0),
            # Per-region live vs baseline tanker share, so the vessel term can be
            # audited rather than taken on trust.
            "vessel_density_detail": sdi_data.get("vessel_density_detail", {}),
            "market_status":    sdi_data.get("market_status", "unavailable"),
            "event_source_at":  sdi_data.get("event_source_at"),
            "vessel_source_at": sdi_data.get("vessel_source_at"),
            "market_source_date": sdi_data.get("market_source_date"),
            "computed_at":      sdi_data.get("computed_at"),
            "updated_at":       sdi_data.get("updated_at"),
        }
    except ValueError as exc:
        logger.warning("get_live_metrics degraded: %s", exc)
        return {"status": "degraded", "error": str(exc)}
    except Exception as exc:
        logger.error("get_live_metrics failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/risk/events")
def get_risk_events(limit: int = 10) -> list[dict[str, Any]]:
    """
    Return the latest Sentinel-scored geopolitical risk events.
    Powers the Risk Intelligence tab event feed.
    """
    try:
        events = fetch_risk_events(limit=limit)
        result = []
        for e in events:
            # Convert severity float to human label for UI badge
            sev = float(e.get("severity", 0) or 0)
            if sev >= 0.8:
                label = "CRITICAL"
            elif sev >= 0.6:
                label = "HIGH"
            elif sev >= 0.35:
                label = "MODERATE"
            else:
                label = "LOW"

            cps = e.get("affected_chokepoints") or []
            # Postgres may return JSON string; normalise to list
            if isinstance(cps, str):
                try:
                    cps = json.loads(cps)
                except Exception:
                    cps = []

            result.append({
                "id":               e.get("id", 0),
                "region":           e.get("region", "Unknown"),
                "disruption_type":  e.get("disruption_type", "unknown"),
                "severity":         round(sev, 3),
                "severity_label":   label,
                "severity_reasoning": e.get("severity_reasoning", ""),
                "affected_chokepoints": cps,
                "affected_producer_countries": list(dict.fromkeys(
                    canonical_country_name(country)
                    for country in (e.get("affected_producer_countries") or [])
                )),
                "directly_affected_producer_countries": e.get(
                    "directly_affected_producer_countries", []
                ) or [],
                "summary":          e.get("summary", ""),
                "sdi_score":        float(e.get("sdi_score", 0) or 0),
                "scored_at":        str(e.get("created_at", "")),
                "source_fetched_at": str(e.get("source_fetched_at", "")),
                "source_urls":      e.get("source_urls", []),
            })
        return result
    except Exception as exc:
        logger.error("get_risk_events failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/risk/events/{event_id}")
def get_risk_event_detail(event_id: int) -> dict[str, Any]:
    """
    Return detailed information for a single risk event, including
    potentially affected crude grades from Neo4j.
    """
    try:
        e = fetch_risk_event(event_id)
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")

        sev = float(e.get("severity", 0) or 0)
        if sev >= 0.8:
            label = "CRITICAL"
        elif sev >= 0.6:
            label = "HIGH"
        elif sev >= 0.35:
            label = "MODERATE"
        else:
            label = "LOW"

        cps = e.get("affected_chokepoints") or []
        if isinstance(cps, str):
            try:
                cps = json.loads(cps)
            except Exception:
                cps = []
                
        prods = e.get("affected_producer_countries") or []
        if isinstance(prods, str):
            try:
                prods = json.loads(prods)
            except Exception:
                prods = []
        prods = list(dict.fromkeys(canonical_country_name(p) for p in prods))
        graph_prods = set(prods)
        graph_prods.update(
            alias for alias, canonical in COUNTRY_ALIASES.items()
            if canonical in prods
        )

        affected_grades = []
        driver = get_driver()
        if driver and (prods or cps):
            with driver.session() as session:
                query = """
                MATCH (p:ExportPort)-[:EXPORTS]->(g:CrudeGrade)
                WHERE p.country IN $countries
                RETURN DISTINCT g.name AS grade
                UNION
                MATCH (p:ExportPort)-[:EXPORTS]->(g:CrudeGrade), (p)-[:SHIPS_THROUGH]->(c:Chokepoint)
                WHERE c.name IN $chokepoints
                RETURN DISTINCT g.name AS grade
                """
                res = session.run(query, countries=list(graph_prods), chokepoints=cps)
                affected_grades = [r["grade"] for r in res]

        inferred_cps = []
        if not cps and prods:
            for p in prods:
                for mapped_country, mapped_chokepoints in PRODUCER_TO_CHOKEPOINTS.items():
                    if canonical_country_name(mapped_country) != p:
                        continue
                    for cp in mapped_chokepoints:
                        if cp not in inferred_cps:
                            inferred_cps.append(cp)

        return {
            "id":               e.get("id", 0),
            "region":           e.get("region", "Unknown"),
            "disruption_type":  e.get("disruption_type", "unknown"),
            "severity":         round(sev, 3),
            "severity_label":   label,
            "severity_reasoning": e.get("severity_reasoning", ""),
            "affected_chokepoints": cps,
            "inferred_chokepoints": inferred_cps,
            "affected_producer_countries": prods,
            "directly_affected_producer_countries": e.get(
                "directly_affected_producer_countries", []
            ) or [],
            "affected_grades":  affected_grades,
            "summary":          e.get("summary", ""),
            "sdi_score":        float(e.get("sdi_score", 0) or 0),
            "scored_at":        str(e.get("created_at", "")),
            "source_fetched_at": str(e.get("source_fetched_at", "")),
            "source_urls":      e.get("source_urls", []),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_risk_event_detail failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/risk/chokepoints")
def get_chokepoint_matrix() -> list[dict[str, Any]]:
    """
    Return the per-chokepoint risk matrix with flow, risk score, and price impact.
    Powers the Risk Intelligence → Chokepoint Risk Matrix table.
    """
    try:
        return compute_chokepoint_risk_matrix()
    except ValueError as exc:
        logger.warning("get_chokepoint_matrix degraded: %s", exc)
        return [{"status": "degraded", "error": str(exc)}]
    except Exception as exc:
        logger.error("get_chokepoint_matrix failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/risk/chokepoints/{name}")
def get_chokepoint_detail(name: str) -> dict[str, Any]:
    """Score attribution for one chokepoint — which events drove it and how."""
    try:
        detail = explain_chokepoint_risk(name)
        if not detail:
            raise HTTPException(status_code=404, detail="Chokepoint not tracked")
        return detail
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_chokepoint_detail failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/risk/producers/{name}")
def get_producer_detail(name: str) -> dict[str, Any]:
    """Score attribution for one producer country."""
    try:
        detail = explain_producer_risk(name)
        if not detail:
            raise HTTPException(status_code=404, detail="Producer not tracked")
        return detail
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_producer_detail failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/risk/producers")
def get_producer_matrix() -> list[dict[str, Any]]:
    """
    Return the per-producer risk matrix.
    Powers the Risk Intelligence → Producer Risk Matrix table.
    """
    try:
        return compute_producer_country_risk_matrix()
    except ValueError as exc:
        logger.warning("get_producer_matrix degraded: %s", exc)
        return [{"status": "degraded", "error": str(exc)}]
    except Exception as exc:
        logger.error("get_producer_matrix failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/risk/sdi-timeline")
def get_sdi_timeline() -> list[dict[str, Any]]:
    """Return persisted canonical SDI computations for the timeline chart."""
    try:
        snapshots = fetch_sdi_snapshots(limit=50)
        if not snapshots:
            # Startup normally persists a first point. This local-cache-only
            # fallback keeps a fresh installation usable if persistence failed.
            live = compute_current_sdi()
            return [{
                "scored_at": live["computed_at"],
                "sdi_score": live["sdi_score"],
                "confidence_low": live["confidence_low"],
                "confidence_high": live["confidence_high"],
                "ais_status": live.get("ais_status"),
                "market_status": live.get("market_status"),
            }]

        return [
            {
                "scored_at": str(snapshot.get("computed_at", "")),
                "sdi_score": round(float(snapshot.get("sdi_score", 0.0)), 1),
                "confidence_low": round(
                    float(snapshot.get("confidence_low", 0.0) or 0.0),
                    1,
                ),
                "confidence_high": round(
                    float(snapshot.get("confidence_high", 0.0) or 0.0),
                    1,
                ),
                "p_risk": float(snapshot.get("p_risk", 0.0) or 0.0),
                "delta_d": float(snapshot.get("delta_d", 0.0) or 0.0),
                "delta_p": float(snapshot.get("delta_p", 0.0) or 0.0),
                "delta_f": float(snapshot.get("delta_f", 0.0) or 0.0),
                "ais_status": snapshot.get("ais_status"),
                "market_status": snapshot.get("market_status"),
                "event_source_at": str(snapshot.get("event_source_at") or ""),
                "vessel_source_at": str(snapshot.get("vessel_source_at") or ""),
                "market_source_date": str(
                    snapshot.get("market_source_date") or ""
                ),
            }
            for snapshot in reversed(snapshots)
        ]
    except Exception as exc:
        logger.error("get_sdi_timeline failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/market/prices")
def get_market_prices() -> dict[str, Any]:
    """
    Return the latest price snapshot for all tracked tickers.
    Powers the Market Pulse tab.
    """
    try:
        tickers = ["BZ=F", "NG=F", "USO", "XLE"]
        prices_raw = fetch_latest_prices(tickers=tickers, days=60)

        # Group by ticker, sort by date
        by_ticker: dict[str, list] = {t: [] for t in tickers}
        for row in prices_raw:
            t = row.get("ticker", "")
            if t in by_ticker:
                by_ticker[t].append(row)

        for t in by_ticker:
            by_ticker[t].sort(key=lambda r: str(r.get("trade_date", "")))

        # Build summary card per ticker
        summaries = []
        for t in tickers:
            rows = by_ticker[t]
            if rows:
                latest = rows[-1]
                close_prices = [float(r.get("price_close", 0) or 0) for r in rows]
                summaries.append({
                    "ticker":     t,
                    "price":      round(float(latest.get("price_close", 0) or 0), 2),
                    "high_52w":   round(max(close_prices) if close_prices else 0, 2),
                    "low_52w":    round(min(close_prices) if close_prices else 0, 2),
                    "volume":     int(latest.get("volume", 0) or 0),
                    "series":     [
                        {
                            "d":     str(r.get("trade_date", ""))[:10],
                            "price": round(float(r.get("price_close", 0) or 0), 2),
                            "ma":    round(float(r.get("price_close", 0) or 0), 2),
                        }
                        for i, r in enumerate(rows[-60:])
                    ],
                })
            else:
                summaries.append({"ticker": t, "price": 0, "high_52w": 0, "low_52w": 0, "volume": 0, "series": []})

        brent_stats = get_brent_rolling_stats()
        return {
            "instruments": summaries,
            "brent_current": brent_stats["current_price"],
            "brent_mean_30d": brent_stats["rolling_mean"],
            "brent_std_30d": brent_stats["rolling_std"],
        }
    except Exception as exc:
        logger.error("get_market_prices failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/market/vessels")
def get_vessels() -> list[dict[str, Any]]:
    """Return vessel positions for the Threat Map."""
    try:
        vessels = fetch_vessels()
        return [
            {
                "mmsi":        v.get("mmsi"),
                "vessel_name": v.get("vessel_name", "Unknown"),
                "lat":         v.get("lat"),
                "lon":         v.get("lon"),
                "speed":       v.get("speed"),
                "region":      v.get("region", "Unknown"),
            }
            for v in vessels
        ]
    except Exception as exc:
        logger.error("get_vessels failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Endpoints: Configuration Lists (drive dropdowns) ─────────────────────────

@app.get("/api/config/chokepoints")
def list_chokepoints() -> list[str]:
    """Return the canonical list of tracked chokepoints for UI dropdown options."""
    try:
        return get_chokepoint_list()
    except Exception as exc:
        logger.error("list_chokepoints failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/config/refineries")
def list_refineries() -> list[str]:
    """Return available destination refineries for UI dropdown options."""
    try:
        return get_refinery_list()
    except Exception as exc:
        logger.error("list_refineries failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/config/grades")
def list_grades() -> list[str]:
    """Return available crude grades for UI dropdown options."""
    try:
        return get_crude_grade_list()
    except Exception as exc:
        logger.error("list_grades failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Endpoints: Agent Orchestration ───────────────────────────────────────────

@app.post("/api/orchestrator/reroute")
def run_reroute(req: RerouteRequest) -> dict[str, Any]:
    """
    Run the 5-step Adaptive Procurement Orchestrator (Fixer Agent).
    Returns a ranked procurement matrix of alternative crude sources.
    """
    try:
        result = find_alternatives(
            blocked_chokepoint=req.blocked_chokepoint,
            crude_grade=req.crude_grade,
            ranking_mode=req.ranking_mode,
            destination_refinery=req.destination_refinery,
            excluded_countries=req.excluded_countries,
            strict_grade_match=req.strict_grade_match,
        )
        pm = result.get("procurement_matrix", [])
        # Mark top pick for the UI
        for i, row in enumerate(pm):
            row["top"] = (i == 0)
        return {
            "procurement_matrix":   pm,
            "diagnostic":           result.get("diagnostic"),
            "resilience_score":     result.get("resilience_score", 0),
            "current_brent_usd":    result.get("current_brent_usd", 0),
            "grade_filtered":       result.get("grade_filtered", False),
            "destination_refinery": result.get("destination_refinery", ""),
            "refinery_options":     result.get("refinery_options", []),
            "freight_params":       result.get("freight_params", {}),
            "context_events":       result.get("context_events", []),
        }
    except Exception as exc:
        logger.error("run_reroute failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/orchestrator/spr")
def run_spr(req: SprRequest) -> dict[str, Any]:
    """
    Run the SPR burn-down model.
    Returns survival days, supply gap, demand actions, and macro impact.
    """
    try:
        result = calculate_spr_impact(
            lead_time_days=req.lead_time_days,
            blocked_chokepoint=req.blocked_chokepoint,
            disrupted_volume_mbpd=req.disrupted_volume_mbpd,
            gdp_impact_rate=req.gdp_impact_rate,
            run_rate_cut=req.run_rate_cut,
            industrial_cut=req.industrial_cut,
            transport_cut=req.transport_cut,
        )
        # Convert burndown DataFrame to JSON-serialisable list
        burndown_df = result.pop("burndown_df", None)
        burndown_list = []
        if burndown_df is not None:
            burndown_list = [
                {
                    "day":      int(row["Day"]),
                    "baseline": round(float(row["SPR Level (MB)"]) / float(result.get("spr_capacity_mb", 39)) * 100, 1),
                    "managed":  round(float(row["SPR Managed (MB)"]) / float(result.get("spr_capacity_mb", 39)) * 100, 1),
                }
                for _, row in burndown_df.iterrows()
            ]
        return {**result, "burndown_series": burndown_list}
    except Exception as exc:
        logger.error("run_spr failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/orchestrator/war-room")
def run_war_room(req: WarRoomRequest) -> dict[str, Any]:
    """
    Run the full War Room pipeline:
      1. Fixer Agent (reroute)
      2. SPR Modeler (burn-down)
      3. Briefing Agent (LLM executive brief)

    Returns combined payload for the War Room tab.
    """
    try:
        # Step 1: Reroute
        fixer_result = find_alternatives(
            blocked_chokepoint=req.blocked_chokepoint,
            crude_grade=req.crude_grade,
            ranking_mode=req.ranking_mode,
            destination_refinery=req.destination_refinery,
            excluded_countries=req.excluded_countries,
            strict_grade_match=req.strict_grade_match,
        )
        pm = fixer_result.get("procurement_matrix", [])
        diagnostic = fixer_result.get("diagnostic")
        if not pm:
            if diagnostic:
                return {"top_routes": [], "diagnostic": diagnostic}
            raise HTTPException(status_code=422, detail="No viable reroute alternatives found in graph DB.")

        top = pm[0]
        lead_time = float(top.get("lead_time_days", 22))

        # Step 2: SPR
        spr = calculate_spr_impact(
            lead_time_days=lead_time,
            blocked_chokepoint=req.blocked_chokepoint,
            disrupted_volume_mbpd=req.disrupted_volume_mbpd,
            gdp_impact_rate=req.gdp_impact_rate,
            run_rate_cut=req.run_rate_cut,
            industrial_cut=req.industrial_cut,
            transport_cut=req.transport_cut,
        )
        burndown_df = spr.pop("burndown_df", None)
        burndown_list = []
        if burndown_df is not None:
            cap = float(spr.get("spr_capacity_mb", 39))
            burndown_list = [
                {
                    "day":      int(row["Day"]),
                    "baseline": round(float(row["SPR Level (MB)"]) / cap * 100, 1),
                    "managed":  round(float(row["SPR Managed (MB)"]) / cap * 100, 1),
                }
                for _, row in burndown_df.iterrows()
            ]

        # Step 3: Executive Brief
        df_for_brief = pd.DataFrame(pm[:3]).rename(columns={
            "export_port":     "Export Terminal",
            "crude_grade":     "Crude Grade",
            "landed_cost_usd": "Landed Cost ($/bbl)",
            "lead_time_days":  "Lead Time (days)",
        })
        briefing_text = generate_emergency_brief(
            scenario_name=req.scenario_name,
            target_refinery=req.destination_refinery or "Jamnagar",
            spr_data=spr,
            reroute_df=df_for_brief,
        )

        return {
            "top_routes": [
                {
                    "terminal": r.get("export_port", ""),
                    "grade":    r.get("crude_grade", ""),
                    "landed":   f"${float(r.get('landed_cost_usd', 0)):.2f}",
                    "lead":     f"{float(r.get('lead_time_days', 0)):.1f} days",
                    "match_type": r.get("match_type", "exact"),
                    "match_reason": r.get("match_reason", ""),
                }
                for r in pm[:5]
            ],
            "spr_trajectory": {
                "survival_days":  spr.get("survival_days", 0),
                "supply_gap_days": spr.get("supply_gap_days", 0),
                "gdp_impact":     spr.get("macro_gdp_impact_pct", "—"),
                "infl_impact":    spr.get("macro_infl_impact", "—"),
                "recommendation": spr.get("recommendation", ""),
                "status_color":   spr.get("status_color", "green"),
            },
            "burndown_series": burndown_list,
            "executive_brief": briefing_text,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("run_war_room failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/backtest/jobs")
def get_backtest_jobs() -> list[dict[str, Any]]:
    """Return all backtest jobs (pending, running, completed, failed)."""
    try:
        return fetch_all_backtest_jobs()
    except Exception as exc:
        logger.error("get_backtest_jobs failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/backtest/trigger")
def trigger_backtest(req: BacktestRequest) -> dict[str, Any]:
    """Create a backtest job and start it immediately in this process.

    Previously this only inserted a `pending` row and the cron worker picked
    it up on a 30-second poll. That poll queried Postgres twice a minute in
    perpetuity, which stopped a serverless database ever going idle — see
    backtest_dispatch. Running it here removes the poll and starts the job now
    rather than up to 30 s later.
    """
    try:
        job_id = create_backtest_job(req.event_name)
        if not job_id:
            raise HTTPException(status_code=500, detail="Failed to create backtest job.")

        if not dispatch_backtest(job_id, req.event_name):
            # Capped for memory: concurrent backtests are what put a 512 MB
            # instance over the edge. Fail the row too, so it does not sit at
            # "pending" forever waiting for a poller that no longer exists.
            update_backtest_job(
                job_id, "failed", "Server busy — another backtest is already running."
            )
            raise HTTPException(
                status_code=503,
                detail="Another backtest is already running. Try again shortly.",
            )

        return {"job_id": job_id, "status": "running"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("trigger_backtest failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/backtest/{event_name}")
def get_backtest(
    event_name: str,
    sdi_threshold: float = 65.0,
) -> dict[str, Any]:
    """
    Return the historical backtest time-series and computed verdict for the given event.
    Combines daily SDI scores with Brent prices to show lead time.
    """
    try:
        if not 0.0 <= sdi_threshold <= 100.0:
            raise HTTPException(
                status_code=422,
                detail="sdi_threshold must be between 0 and 100.",
            )
        events = fetch_risk_events_backtest(event_name)
        if not events:
            raise HTTPException(status_code=404, detail="No backtest data found for this event.")
            
        prices = fetch_latest_prices(tickers=["BZ=F"], days=2000) # ensure we get all data going back to 2023
        
        price_records = [
            {"date": str(p["trade_date"]), "price": float(p["price_close"])}
            for p in prices if p.get("ticker") == "BZ=F"
        ]
        price_df = pd.DataFrame(price_records)
        if not price_df.empty:
            price_df["date"] = pd.to_datetime(price_df["date"]).dt.date
            price_df.sort_values("date", inplace=True)
            price_df.set_index("date", inplace=True)
            
            # Calculate 14-day rolling mean and std to detect short-term breakouts
            price_df["mean_14d"] = price_df["price"].rolling(14).mean()
            price_df["std_14d"] = price_df["price"].rolling(14).std()
        
        # Build timeline mapping from SDI events (max SDI per day)
        timeline_dict = {}
        for ev in events:
            d = ev["created_at"].date()
            sdi = float(ev.get("sdi_score", 0) or 0)
            p_risk = float(ev.get("severity", 0) or 0)
            conf = float(ev.get("confidence", 1.0) or 1.0)
            if d not in timeline_dict or sdi > timeline_dict[d]["sdi"]:
                timeline_dict[d] = {"sdi": sdi, "p_risk": p_risk, "conf": conf}
                
        series = []
        system_alert_date = None
        market_reaction_date = None
        
        start_date = min(timeline_dict.keys())
        end_date = max(timeline_dict.keys())
        
        current = start_date
        while current <= end_date:
            day_data = timeline_dict.get(current, {"sdi": 0.0, "p_risk": 0.0, "conf": 1.0})
            sdi = day_data["sdi"]
            p_risk = day_data["p_risk"]
            conf = day_data["conf"]
            
            sdi_component = p_risk * 50.0
            margin = sdi_component * (1.0 - conf)
            
            p_val = None
            mean_val = None
            std_val = None
            
            if not price_df.empty:
                if current in price_df.index:
                    row = price_df.loc[current]
                else:
                    subset = price_df[price_df.index <= current]
                    row = subset.iloc[-1] if not subset.empty else None
                    
                if row is not None:
                    p_val = float(row["price"])
                    mean_val = float(row["mean_14d"]) if pd.notna(row["mean_14d"]) else p_val
                    std_val = float(row["std_14d"]) if pd.notna(row["std_14d"]) else 0.0
                    
            if p_val is not None:
                series.append({
                    "date": current.isoformat(),
                    "sdi_score": round(sdi, 1),
                    "confidence_low": round(max(0.0, sdi - margin), 1),
                    "confidence_high": round(min(100.0, sdi + margin), 1),
                    "brent_price": round(p_val, 2)
                })
                
                # System alert first time we cross threshold
                if system_alert_date is None and sdi >= sdi_threshold:
                    system_alert_date = current
                    
                # Market reaction first time price breaks +1.5 std (independent of alert)
                if market_reaction_date is None and p_val > (mean_val + 1.5 * std_val):
                    market_reaction_date = current
                        
            current += timedelta(days=1)
            
        verdict = "System did not generate an alert before the market reacted."
        lead_time_days = 0
        if system_alert_date and market_reaction_date:
            lead_time_days = (market_reaction_date - system_alert_date).days
            if lead_time_days > 0:
                verdict = f"System flagged elevated risk {lead_time_days} days before Brent crude moved >1.5σ above trend."
            elif lead_time_days == 0:
                verdict = "System flagged risk contemporaneously with market reaction."
            else:
                verdict = f"System lagged the market: alert triggered {abs(lead_time_days)} days after price breakout."
                
        sensitivity = []
        for threshold in (50, 55, 60, 65, 70, 75, 80):
            alert_row = next(
                (row for row in series if row["sdi_score"] >= threshold),
                None,
            )
            alert_date = date.fromisoformat(alert_row["date"]) if alert_row else None
            sensitivity.append({
                "threshold": threshold,
                "alert_date": alert_row["date"] if alert_row else None,
                "lead_time_days": (
                    (market_reaction_date - alert_date).days
                    if alert_date and market_reaction_date
                    else 0
                ),
            })

        return {
            "series": series,
            "system_alert_date": system_alert_date.isoformat() if system_alert_date else None,
            "market_reaction_date": market_reaction_date.isoformat() if market_reaction_date else None,
            "lead_time_days": lead_time_days,
            "verdict": verdict,
            "sdi_threshold": sdi_threshold,
            "threshold_sensitivity": sensitivity,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_backtest failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
