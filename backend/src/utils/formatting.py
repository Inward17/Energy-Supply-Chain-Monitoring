"""
src/utils/formatting.py
───────────────────────
Streamlit layout helpers: badge HTML, DataFrame transformers,
and chart data preparation. No business logic lives here.
"""

from __future__ import annotations

import pandas as pd
from typing import Any


# ---------------------------------------------------------------------------
# Risk Badge HTML
# ---------------------------------------------------------------------------

_SEVERITY_THRESHOLDS = [
    (0.75, "#e74c3c", "🔴 CRITICAL"),
    (0.50, "#e67e22", "🟠 HIGH"),
    (0.25, "#f1c40f", "🟡 MODERATE"),
    (0.0,  "#2ecc71", "🟢 LOW"),
]


def risk_badge(severity: float) -> str:
    """
    Return an HTML badge string for a severity score (0–1).

    Use inside st.markdown(..., unsafe_allow_html=True).
    """
    for threshold, colour, label in _SEVERITY_THRESHOLDS:
        if severity >= threshold:
            return (
                f'<span style="background:{colour};color:#fff;padding:3px 10px;'
                f'border-radius:12px;font-size:0.78rem;font-weight:700;">{label}</span>'
            )
    return '<span style="background:#7f8c8d;color:#fff;padding:3px 10px;border-radius:12px;">UNKNOWN</span>'


def sdi_color(sdi_score: float) -> str:
    """Return a hex colour appropriate for an SDI value (0–100)."""
    if sdi_score >= 75:
        return "#e74c3c"
    elif sdi_score >= 50:
        return "#e67e22"
    elif sdi_score >= 25:
        return "#f1c40f"
    return "#2ecc71"


# ---------------------------------------------------------------------------
# Vessel DataFrame Formatter
# ---------------------------------------------------------------------------

def format_vessel_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Convert raw vessel_telemetry rows from Postgres into a display DataFrame.

    Args:
        rows: List of dicts from postgres_db.fetch_vessels().

    Returns:
        Cleaned DataFrame ready for PyDeck/Folium and st.dataframe().
    """
    if not rows:
        return pd.DataFrame(columns=["mmsi", "vessel_name", "lat", "lon", "speed", "region", "recorded_at"])

    df = pd.DataFrame(rows)

    # Rename for display
    col_map = {
        "mmsi": "MMSI",
        "vessel_name": "Vessel Name",
        "lat": "lat",
        "lon": "lon",
        "speed": "Speed (kn)",
        "heading": "Heading°",
        "region": "Region",
        "recorded_at": "Last Seen",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Coerce numeric columns
    for col in ["lat", "lon", "Speed (kn)"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Format timestamp
    if "Last Seen" in df.columns:
        df["Last Seen"] = pd.to_datetime(df["Last Seen"], utc=True, errors="coerce").dt.strftime("%Y-%m-%d %H:%M UTC")

    # Drop rows with null coordinates (can't plot them)
    df = df.dropna(subset=["lat", "lon"])

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Price Chart DataFrame Formatter
# ---------------------------------------------------------------------------

def format_price_chart_df(rows: list[dict[str, Any]], ticker: str) -> pd.DataFrame:
    """
    Prepare a price time-series DataFrame for Plotly Candlestick / Line charts.

    Args:
        rows:   List of market_prices rows from postgres_db.fetch_latest_prices().
        ticker: Ticker symbol to filter (e.g. 'BZ=F').

    Returns:
        DataFrame with columns: date, open, high, low, close, volume.
    """
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows)

    if "ticker" in df.columns:
        df = df[df["ticker"] == ticker].copy()

    rename_map = {
        "trade_date":   "date",
        "price_open":   "open",
        "price_close":  "close",
        "price_high":   "high",
        "price_low":    "low",
        "volume":       "volume",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date")

    for col in ["open", "close", "high", "low"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna(subset=["date", "close"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Risk Events Formatter
# ---------------------------------------------------------------------------

def format_risk_events_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Format risk_events rows for display in the Risk Intelligence tab.

    Args:
        rows: List of dicts from postgres_db.fetch_risk_events().

    Returns:
        Styled DataFrame.
    """
    if not rows:
        return pd.DataFrame(columns=["Region", "Type", "Severity", "SDI", "Chokepoints", "Summary", "Time"])

    df = pd.DataFrame(rows)

    rename_map = {
        "region":               "Region",
        "disruption_type":      "Type",
        "severity":             "Severity",
        "sdi_score":            "SDI",
        "affected_chokepoints": "Chokepoints",
        "summary":              "Summary",
        "created_at":           "Time",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "Time" in df.columns:
        df["Time"] = pd.to_datetime(df["Time"], utc=True, errors="coerce").dt.strftime("%Y-%m-%d %H:%M UTC")

    if "Severity" in df.columns:
        df["Severity"] = df["Severity"].apply(lambda s: f"{float(s):.0%}" if pd.notna(s) else "–")

    if "SDI" in df.columns:
        df["SDI"] = df["SDI"].apply(lambda s: f"{float(s):.1f}" if pd.notna(s) else "–")

    if "Chokepoints" in df.columns:
        df["Chokepoints"] = df["Chokepoints"].apply(
            lambda v: ", ".join(v) if isinstance(v, list) else str(v)
        )

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# PyDeck Layer Data
# ---------------------------------------------------------------------------

def vessels_to_pydeck_data(df: pd.DataFrame) -> list[dict]:
    """Convert vessel DataFrame to list of dicts for PyDeck ScatterplotLayer."""
    if df.empty:
        return []
    records = df[["lat", "lon", "MMSI", "Vessel Name", "Speed (kn)", "Region"]].copy()
    records.columns = ["lat", "lon", "mmsi", "name", "speed", "region"]
    return records.to_dict(orient="records")


def risk_events_to_heatmap_data(rows: list[dict[str, Any]]) -> list[dict]:
    """
    Map risk events to approximate chokepoint coordinates for a PyDeck HeatmapLayer.
    """
    CHOKEPOINT_COORDS = {
        "Strait of Hormuz":    {"lat": 26.56,  "lon": 56.25},
        "Suez Canal":          {"lat": 30.58,  "lon": 32.26},
        "Bab-el-Mandeb":       {"lat": 12.58,  "lon": 43.41},
        "Strait of Malacca":   {"lat": 1.25,   "lon": 103.82},
        "Cape of Good Hope":   {"lat": -34.35, "lon": 18.47},
        "Panama Canal":        {"lat": 9.08,   "lon": -79.68},
        "Turkish Straits":     {"lat": 41.11,  "lon": 29.07},
        "Strait of Gibraltar": {"lat": 35.98,  "lon": -5.49},
    }

    heatmap = []
    for row in rows:
        chokepoints = row.get("affected_chokepoints") or []
        severity = float(row.get("severity", 0.5))
        for cp in chokepoints:
            coords = CHOKEPOINT_COORDS.get(cp)
            if coords:
                heatmap.append({**coords, "weight": severity})
    return heatmap
