import os
import sys
import logging
import pandas as pd
from datetime import datetime, timedelta, date, timezone
import yfinance as yf

# Ensure we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from src.ingestion.gdelt_collector import fetch_historical
from src.ingestion.market_trawler import fetch_historical_prices
from src.agents.sentinel_agent import _build_prompt, _call_gemini
from src.agents.modeler_agent import normalise_price_delta, normalise_freight_delta, supply_disruption_index
from src.database.postgres_db import upsert_risk_event_backtest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVENT_NAME = "red_sea_attacks"
START_DATE_STR = "2023-11-15"
END_DATE_STR = "2024-01-31"

def run_backtest():
    start_date = datetime.strptime(START_DATE_STR, "%Y-%m-%d").date()
    end_date = datetime.strptime(END_DATE_STR, "%Y-%m-%d").date()
    
    # We need a 30-day buffer for rolling stats
    buffer_start = start_date - timedelta(days=45) 
    
    logger.info("Fetching historical Brent prices to compute rolling stats...")
    fetch_historical_prices(buffer_start.strftime("%Y-%m-%d"), (end_date + timedelta(days=1)).strftime("%Y-%m-%d"), ["BZ=F", "BOAT"])
    
    # Download prices into pandas to calculate rolling stats efficiently
    df_brent = yf.download("BZ=F", start=buffer_start.strftime("%Y-%m-%d"), end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
    if hasattr(df_brent.columns, "levels"):
        df_brent.columns = df_brent.columns.get_level_values(0)
    
    df_brent["Close"] = df_brent["Close"].astype(float)
    df_brent["Rolling_Mean"] = df_brent["Close"].rolling(30).mean()
    df_brent["Rolling_Std"] = df_brent["Close"].rolling(30).std()

    # Freight
    df_freight = yf.download("BOAT", start=buffer_start.strftime("%Y-%m-%d"), end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
    if hasattr(df_freight.columns, "levels"):
        df_freight.columns = df_freight.columns.get_level_values(0)
    
    df_freight["Close"] = df_freight["Close"].astype(float)
    df_freight["Rolling_Mean"] = df_freight["Close"].rolling(30).mean()
    df_freight["Rolling_Std"] = df_freight["Close"].rolling(30).std()
    
    current_date = start_date
    
    # Pre-fetch existing events to skip them
    from src.database.postgres_db import fetch_risk_events_backtest
    import time
    existing_events = fetch_risk_events_backtest(EVENT_NAME)
    existing_dates = {ev["created_at"].date() for ev in existing_events}
    
    while current_date <= end_date:
        logger.info(f"--- Processing {current_date} ---")
        
        if current_date in existing_dates:
            logger.info(f"Date {current_date} already exists. Skipping.")
            current_date += timedelta(days=1)
            continue
            
        # 1. Get Brent and Freight stats for this date
        # We find the closest previous trading day if current_date is a weekend
        subset_brent = df_brent[df_brent.index.date <= current_date]
        subset_freight = df_freight[df_freight.index.date <= current_date]
        
        if subset_brent.empty or subset_freight.empty:
            logger.warning(f"No price data before {current_date}. Skipping.")
            current_date += timedelta(days=1)
            continue
            
        latest_row_b = subset_brent.iloc[-1]
        brent_stats = {
            "current_price": float(latest_row_b["Close"]),
            "rolling_mean": float(latest_row_b["Rolling_Mean"]) if pd.notna(latest_row_b["Rolling_Mean"]) else float(latest_row_b["Close"]),
            "rolling_std": float(latest_row_b["Rolling_Std"]) if pd.notna(latest_row_b["Rolling_Std"]) else 1.0,
        }

        latest_row_f = subset_freight.iloc[-1]
        freight_stats = {
            "current_price": float(latest_row_f["Close"]),
            "rolling_mean": float(latest_row_f["Rolling_Mean"]) if pd.notna(latest_row_f["Rolling_Mean"]) else float(latest_row_f["Close"]),
            "rolling_std": float(latest_row_f["Rolling_Std"]) if pd.notna(latest_row_f["Rolling_Std"]) else 1.0,
        }
        
        # Sleep to avoid GDELT rate limits
        time.sleep(10)
        
        # 2. Fetch GDELT news
        startdatetime = current_date.strftime("%Y%m%d000000")
        enddatetime = (current_date + timedelta(days=1)).strftime("%Y%m%d000000")
        articles = fetch_historical(startdatetime, enddatetime)
        
        # Pick top 10 articles to stay within prompt limits
        headlines = [a["title"] for a in articles[:10]]
        
        if not headlines:
            logger.info("No articles found (or rate limit hit). Scoring as 0.")
            scored = {"severity": 0.0, "region": "Global", "disruption_type": "None", "summary": "No news", "confidence": 1.0}
        else:
            # 3. Call Gemini
            prompt = _build_prompt(headlines)
            while True:
                try:
                    scored = _call_gemini(prompt)
                    if not scored:
                        logger.warning("Gemini returned empty. Retrying in 60s...")
                        time.sleep(60)
                        continue
                    break # Success
                except Exception as exc:
                    logger.error("Gemini call failed: %s. Retrying in 60s...", exc)
                    time.sleep(60)
            
        # 4. Compute SDI
        delta_p = normalise_price_delta(
            current_price=brent_stats["current_price"],
            rolling_mean=brent_stats["rolling_mean"],
            rolling_std=brent_stats["rolling_std"],
        )
        
        delta_f = normalise_freight_delta(
            current_freight=freight_stats["current_price"],
            rolling_mean=freight_stats["rolling_mean"],
            rolling_std=freight_stats["rolling_std"],
        )
        
        # Approximate delta_d for historical backtest without real AIS history
        delta_d = 0.2 if scored.get("severity", 0) > 0.7 else 0.05
        
        sdi = supply_disruption_index(
            p_risk=float(scored.get("severity", 0.0)),
            delta_d_vessel=delta_d,
            delta_p_price=delta_p,
            delta_p_freight=delta_f,
        )
        
        # 5. Insert to DB
        dt = datetime.combine(current_date, datetime.min.time(), tzinfo=timezone.utc)
        event = {
            **scored,
            "event_name": EVENT_NAME,
            "sdi_score": sdi,
            "created_at": dt
        }
        
        upsert_risk_event_backtest(event)
        logger.info(f"Stored event: severity={scored.get('severity')}, SDI={sdi:.2f}")
        
        current_date += timedelta(days=1)

if __name__ == "__main__":
    run_backtest()
