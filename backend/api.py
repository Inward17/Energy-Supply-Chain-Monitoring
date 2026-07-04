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

import logging
from typing import Any
from datetime import datetime, timedelta, date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.utils.schemas import RerouteRequest, SprRequest, WarRoomRequest

# ── Agent imports (untouched business logic) ────────────────────────────────
from src.agents.fixer_agent import (
    find_alternatives,
    get_chokepoint_list,
    get_crude_grade_list,
    get_refinery_list,
)
from src.agents.spr_agent import calculate_spr_impact
from src.agents.briefing_agent import generate_emergency_brief
from src.agents.modeler_agent import compute_current_sdi, compute_chokepoint_risk_matrix
from src.database.postgres_db import (
    fetch_unprocessed_news,
    fetch_vessels,
    fetch_latest_prices,
    fetch_risk_events,
    fetch_latest_sdi,
    fetch_risk_events_backtest
)
from src.ingestion.market_trawler import get_brent_rolling_stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# ── FastAPI setup ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Energy Resilience OS API",
    description="REST bridge between the React frontend and the Python agent layer.",
    version="1.0.0",
)

# Allow the Next.js dev server (port 3000) and production builds to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    """Ensure Postgres schema exists before the first request arrives."""
    try:
        init_schema()
        logger.info("Database schema verified on startup.")
    except Exception as exc:
        logger.warning("Could not verify DB schema on startup: %s", exc)


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
        }
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
                import json as _json
                try:
                    cps = _json.loads(cps)
                except Exception:
                    cps = []

            result.append({
                "id":               e.get("id", 0),
                "region":           e.get("region", "Unknown"),
                "disruption_type":  e.get("disruption_type", "unknown"),
                "severity":         round(sev, 3),
                "severity_label":   label,
                "affected_chokepoints": cps,
                "summary":          e.get("summary", ""),
                "sdi_score":        float(e.get("sdi_score", 0) or 0),
                "scored_at":        str(e.get("created_at", "")),
            })
        return result
    except Exception as exc:
        logger.error("get_risk_events failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/risk/chokepoints")
def get_chokepoint_matrix() -> list[dict[str, Any]]:
    """
    Return the per-chokepoint risk matrix with flow, risk score, and price impact.
    Powers the Risk Intelligence → Chokepoint Risk Matrix table.
    """
    try:
        return compute_chokepoint_risk_matrix()
    except Exception as exc:
        logger.error("get_chokepoint_matrix failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/risk/sdi-timeline")
def get_sdi_timeline() -> list[dict[str, Any]]:
    """
    Return recent SDI snapshots as a time-series for the SDI timeline chart.
    """
    try:
        events = fetch_risk_events(limit=20)
        timeline = []
        for ev in reversed(events):
            scored_at = ev.get("created_at", "")
            sdi_val = float(ev.get("sdi_score", 0) or 0)
            # Include confidence metrics
            p_risk = float(ev.get("severity", 0) or 0)
            conf = float(ev.get("confidence", 1.0) or 1.0)
            sdi_component = p_risk * 50.0
            margin = sdi_component * (1.0 - conf)
            
            timeline.append({
                "scored_at":        str(ev.get("created_at", "")),
                "sdi_score":        round(sdi_val, 1),
                "confidence_low":   round(max(0.0, sdi_val - margin), 1),
                "confidence_high":  round(min(100.0, sdi_val + margin), 1),
            })
        return timeline
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
                            "d":     f"Day {i+1}",
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
        )
        pm = result.get("procurement_matrix", [])
        # Mark top pick for the UI
        for i, row in enumerate(pm):
            row["top"] = (i == 0)
        return {
            "procurement_matrix":   pm,
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
            crude_grade=None,
            ranking_mode="cost",
            destination_refinery=req.destination_refinery,
        )
        pm = fixer_result.get("procurement_matrix", [])
        if not pm:
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
        import pandas as pd
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
                }
                for r in pm[:3]
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

@app.get("/api/backtest/{event_name}")
def get_backtest(event_name: str) -> dict[str, Any]:
    """
    Return the historical backtest time-series and computed verdict for the given event.
    Combines daily SDI scores with Brent prices to show lead time.
    """
    try:
        events = fetch_risk_events_backtest(event_name)
        if not events:
            raise HTTPException(status_code=404, detail="No backtest data found for this event.")
            
        prices = fetch_latest_prices(tickers=["BZ=F"], days=2000) # ensure we get all data going back to 2023
        
        import pandas as pd
        price_records = [
            {"date": str(p["trade_date"]), "price": float(p["price_close"])}
            for p in prices if p.get("ticker") == "BZ=F"
        ]
        price_df = pd.DataFrame(price_records)
        if not price_df.empty:
            price_df["date"] = pd.to_datetime(price_df["date"]).dt.date
            price_df.sort_values("date", inplace=True)
            price_df.set_index("date", inplace=True)
            
            # Calculate 30-day rolling mean and std
            price_df["mean_30d"] = price_df["price"].rolling(30).mean()
            price_df["std_30d"] = price_df["price"].rolling(30).std()
        
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
        SDI_THRESHOLD = 65.0
        
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
                    mean_val = float(row["mean_30d"]) if pd.notna(row["mean_30d"]) else p_val
                    std_val = float(row["std_30d"]) if pd.notna(row["std_30d"]) else 0.0
                    
            if p_val is not None:
                series.append({
                    "date": current.isoformat(),
                    "sdi_score": round(sdi, 1),
                    "confidence_low": round(max(0.0, sdi - margin), 1),
                    "confidence_high": round(min(100.0, sdi + margin), 1),
                    "brent_price": round(p_val, 2)
                })
                
                # System alert first time we cross threshold
                if system_alert_date is None and sdi >= SDI_THRESHOLD:
                    system_alert_date = current
                    
                # Market reaction first time after alert where price breaks +1.5 std
                if system_alert_date is not None and market_reaction_date is None:
                    if p_val > (mean_val + 1.5 * std_val) and current >= system_alert_date:
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
                
        return {
            "series": series,
            "system_alert_date": system_alert_date.isoformat() if system_alert_date else None,
            "market_reaction_date": market_reaction_date.isoformat() if market_reaction_date else None,
            "lead_time_days": lead_time_days,
            "verdict": verdict
        }
    except Exception as exc:
        logger.error("get_backtest failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
