"""
app.py
───────
AI-Driven Energy Supply Chain Resilience OS — Streamlit Dashboard

Entrypoint: streamlit run app.py

Architecture:
  - NEVER makes external network calls directly
  - All data reads from local PostgreSQL via postgres_db (Shadow Cache)
  - Fixer Agent queries local Neo4j for reroute analysis
  - st.cache_data(ttl=60) ensures sub-second repeat loads
  - Auto-refreshes every 60 seconds for live-feel updates

Tabs:
  1. Threat Map       — PyDeck globe with vessel positions + risk heatmap
  2. Risk Intelligence — Sentinel event feed + SDI timeline
  3. Market Pulse     — Brent/NG/XLE candlestick + price impact cards
  4. Reroute Matrix   — Fixer Agent: chokepoint → ranked alternative routes
  5. SPR Optimizer    — Strategic Reserve burn-down + macro-economic impact
  6. War Room         — Scenario Simulator & Executive Briefing Agent
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st
from dotenv import load_dotenv

from src.agents.spr_agent import calculate_spr_impact, SPR_CAPACITY_MB
from src.agents.briefing_agent import generate_emergency_brief
load_dotenv()

# ---------------------------------------------------------------------------
# Page Configuration (must be first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Energy Resilience OS",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — Premium Dark Theme
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    /* Global reset */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #0a0e1a;
        color: #e2e8f0;
    }

    /* Main container */
    .main .block-container {
        padding: 1rem 2rem;
        max-width: 1400px;
    }

    /* Header brand */
    .brand-header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 0.5rem 0 1rem 0;
        border-bottom: 1px solid rgba(59,130,246,0.3);
        margin-bottom: 1.5rem;
    }
    .brand-title {
        font-size: 1.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #3b82f6, #06b6d4, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .brand-sub {
        font-size: 0.78rem;
        color: #64748b;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, rgba(15,23,42,0.9), rgba(30,41,59,0.8));
        border: 1px solid rgba(59,130,246,0.25);
        border-radius: 12px;
        padding: 1rem;
        backdrop-filter: blur(8px);
    }
    [data-testid="metric-container"] label {
        color: #94a3b8 !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #f1f5f9 !important;
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.6rem !important;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(15,23,42,0.6);
        border-radius: 10px;
        padding: 4px;
        gap: 2px;
        border: 1px solid rgba(59,130,246,0.15);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        color: #94a3b8;
        font-weight: 500;
        font-size: 0.85rem;
        padding: 8px 18px;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #3b82f6, #06b6d4) !important;
        color: #fff !important;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0a0e1a 0%, #0f172a 100%);
        border-right: 1px solid rgba(59,130,246,0.15);
    }
    [data-testid="stSidebar"] .element-container {
        color: #e2e8f0;
    }

    /* Selectbox & sliders */
    .stSelectbox > div > div {
        background: rgba(15,23,42,0.8) !important;
        border-color: rgba(59,130,246,0.3) !important;
        color: #e2e8f0 !important;
    }

    /* DataFrames */
    .stDataFrame {
        border: 1px solid rgba(59,130,246,0.2);
        border-radius: 8px;
        overflow: hidden;
    }

    /* Alert boxes */
    .risk-card {
        background: linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.05));
        border: 1px solid rgba(239,68,68,0.3);
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .info-card {
        background: linear-gradient(135deg, rgba(59,130,246,0.15), rgba(59,130,246,0.05));
        border: 1px solid rgba(59,130,246,0.25);
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .sdi-gauge {
        font-family: 'JetBrains Mono', monospace;
        font-size: 2.8rem;
        font-weight: 700;
        text-align: center;
        padding: 1rem 0;
    }

    /* Scrollable event feed */
    .event-feed {
        max-height: 420px;
        overflow-y: auto;
        padding-right: 4px;
    }
    .event-item {
        background: rgba(15,23,42,0.7);
        border-left: 3px solid #3b82f6;
        border-radius: 0 8px 8px 0;
        padding: 0.7rem 1rem;
        margin-bottom: 0.5rem;
        transition: border-color 0.2s;
    }
    .event-item.high   { border-left-color: #ef4444; }
    .event-item.medium { border-left-color: #f97316; }
    .event-item.low    { border-left-color: #22c55e; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Imports (after CSS so page renders immediately)
# ---------------------------------------------------------------------------

from src.database.postgres_db import (
    fetch_risk_events,
    fetch_vessels,
    fetch_latest_prices,
    fetch_latest_sdi,
)
from src.agents.modeler_agent import compute_current_sdi, compute_chokepoint_risk_matrix
from src.agents.fixer_agent import find_alternatives, get_chokepoint_list, get_crude_grade_list, get_refinery_list
from src.utils.formatting import (
    risk_badge,
    sdi_color,
    format_vessel_df,
    format_price_chart_df,
    format_risk_events_df,
    vessels_to_pydeck_data,
    risk_events_to_heatmap_data,
)

# ---------------------------------------------------------------------------
# Cached Data Fetchers (ttl=60s — sub-second after first load)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def cached_sdi() -> dict:
    return compute_current_sdi()


@st.cache_data(ttl=60, show_spinner=False)
def cached_risk_events() -> list:
    return fetch_risk_events(limit=50)


@st.cache_data(ttl=60, show_spinner=False)
def cached_vessels() -> list:
    return fetch_vessels(limit=500)


@st.cache_data(ttl=300, show_spinner=False)
def cached_prices(days: int = 60) -> list:
    return fetch_latest_prices(days=days)


@st.cache_data(ttl=300, show_spinner=False)
def cached_chokepoints() -> list[str]:
    return get_chokepoint_list()


@st.cache_data(ttl=3600, show_spinner=False)
def cached_chokepoint_matrix() -> list:
    return compute_chokepoint_risk_matrix()


@st.cache_data(ttl=3600, show_spinner=False)
def cached_refinery_list() -> list[str]:
    return get_refinery_list()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="brand-header">
        <span style="font-size:2rem;">🛢️</span>
        <div>
            <div class="brand-title">ENERGY SUPPLY CHAIN RESILIENCE OS</div>
            <div class="brand-sub">AI-Driven Global Risk Intelligence Platform · Shadow Cache Architecture</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Controls")

    st.markdown("**Filter by Region**")
    region_filter = st.selectbox(
        "Region",
        ["All Regions", "Strait of Hormuz", "Suez Canal", "Bab-el-Mandeb",
         "Strait of Malacca", "Turkish Straits", "Cape of Good Hope"],
        label_visibility="collapsed",
    )

    st.markdown("**Severity Threshold**")
    severity_threshold = st.slider(
        "Min Severity", 0.0, 1.0, 0.3, 0.05,
        label_visibility="collapsed",
    )

    st.markdown("**Auto-Refresh**")
    auto_refresh = st.toggle("Enable (60s)", value=True)

    st.divider()

    # Live system stats
    sdi_data = cached_sdi()
    st.markdown("### 📊 Live Metrics")

    sdi_val = sdi_data.get("sdi_score", 0)
    col_sdi = sdi_color(sdi_val)
    st.markdown(
        f'<div class="sdi-gauge" style="color:{col_sdi};">{sdi_val:.1f}</div>'
        f'<p style="text-align:center;color:#64748b;font-size:0.75rem;margin-top:-10px;">Supply Disruption Index</p>',
        unsafe_allow_html=True,
    )

    st.metric("🛳️ Vessels Tracked", sdi_data.get("vessel_count", 0))
    st.metric("🚨 Active Alerts",   sdi_data.get("active_alerts", 0))
    st.metric("💰 Brent (USD/bbl)", f"${sdi_data.get('current_brent', 0):.2f}")
    st.metric("📈 Est. Price Impact", f"+${sdi_data.get('price_impact_usd', 0):.2f}/bbl")

    st.divider()
    st.markdown(
        f'<p style="color:#475569;font-size:0.7rem;">Last sync: {datetime.now(timezone.utc).strftime("%H:%M:%S UTC")}</p>',
        unsafe_allow_html=True,
    )

    if st.button("🔄 Force Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# KPI Row
# ---------------------------------------------------------------------------

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
with kpi1:
    st.metric("SDI Score", f"{sdi_val:.1f} / 100",
              delta=f"P_risk={sdi_data.get('p_risk',0):.2f}")
with kpi2:
    st.metric("Top Risk Region", sdi_data.get("top_region", "—"))
with kpi3:
    st.metric("Vessel Density Δ", f"{sdi_data.get('delta_d',0):.2f}",
              delta="vs baseline", delta_color="inverse")
with kpi4:
    st.metric("Brent ΔP (norm)", f"{sdi_data.get('delta_p',0):.2f}")
with kpi5:
    choke_list = sdi_data.get("top_chokepoints", [])
    st.metric("Chokepoints at Risk", len(choke_list),
              delta=", ".join(choke_list[:2]) or "None")

st.divider()

# ---------------------------------------------------------------------------
# Main Tabs
# ---------------------------------------------------------------------------

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🌍 Threat Map",
    "🔴 Risk Intelligence",
    "📈 Market Pulse",
    "🔀 Reroute Matrix",
    "🛢️ SPR Optimizer",
    "⚔️ War Room",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — THREAT MAP
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    st.markdown("#### Live Vessel Positions & Risk Heatmap")

    vessels_raw = cached_vessels()
    events_raw  = cached_risk_events()

    vessel_df = format_vessel_df(vessels_raw)

    # Apply region filter
    if region_filter != "All Regions" and not vessel_df.empty and "Region" in vessel_df.columns:
        vessel_df = vessel_df[vessel_df["Region"] == region_filter]

    vessel_data   = vessels_to_pydeck_data(vessel_df)
    heatmap_data  = risk_events_to_heatmap_data(events_raw)

    # Build PyDeck layers
    vessel_layer = pdk.Layer(
        "ScatterplotLayer",
        data=vessel_data,
        get_position="[lon, lat]",
        get_color="[6, 182, 212, 200]",
        get_radius=25000,
        pickable=True,
        auto_highlight=True,
    )

    heatmap_layer = pdk.Layer(
        "HeatmapLayer",
        data=heatmap_data,
        get_position="[lon, lat]",
        get_weight="weight",
        radiusPixels=80,
        opacity=0.65,
        colorRange=[
            [0, 0, 255, 25],
            [0, 255, 0, 85],
            [255, 255, 0, 128],
            [255, 165, 0, 170],
            [255, 0, 0, 200],
        ],
    )

    view_state = pdk.ViewState(
        latitude=20.0,
        longitude=50.0,
        zoom=2.8,
        pitch=25,
    )

    deck = pdk.Deck(
        map_provider="carto",
        map_style=pdk.map_styles.CARTO_DARK,
        layers=[heatmap_layer, vessel_layer],
        initial_view_state=view_state,
        tooltip={
            "html": "<b>🛳️ {name}</b><br/>MMSI: {mmsi}<br/>Speed: {speed} kn<br/>Region: {region}",
            "style": {"backgroundColor": "#0f172a", "color": "#e2e8f0", "fontSize": "12px"},
        },
    )

    st.pydeck_chart(deck, use_container_width=True)

    # Map legend
    col_l1, col_l2, col_l3 = st.columns(3)
    col_l1.markdown("🔵 **Vessel positions** (cyan dots)")
    col_l2.markdown("🔴 **Risk heatmap** (orange/red = high severity)")
    col_l3.markdown(f"**{len(vessel_data)}** vessels tracked across {region_filter.lower()}")

    # Vessel table (collapsible)
    with st.expander(f"📋 Vessel Data Table ({len(vessel_df)} vessels)"):
        if not vessel_df.empty:
            display_cols = [c for c in ["MMSI", "Vessel Name", "Speed (kn)", "Region", "Last Seen"] if c in vessel_df.columns]
            st.dataframe(vessel_df[display_cols], use_container_width=True, hide_index=True)
        else:
            st.info("No vessel data yet — cron_worker.py will populate this within 15 minutes.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — RISK INTELLIGENCE
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    col_feed, col_chart = st.columns([1, 1])

    with col_feed:
        st.markdown("#### 🚨 Sentinel Risk Event Feed")

        events = cached_risk_events()
        filtered = [e for e in events if float(e.get("severity", 0)) >= severity_threshold]

        if not filtered:
            st.info("No risk events above the severity threshold yet. Cron worker will populate this.")
        else:
            st.markdown('<div class="event-feed">', unsafe_allow_html=True)
            for event in filtered[:15]:
                sev = float(event.get("severity", 0))
                css_class = "high" if sev >= 0.7 else "medium" if sev >= 0.4 else "low"
                chokepoints = ", ".join(event.get("affected_chokepoints") or ["—"])
                ts = event.get("created_at", "")
                if hasattr(ts, "strftime"):
                    ts_str = ts.strftime("%m/%d %H:%M")
                else:
                    ts_str = str(ts)[:16]

                st.markdown(
                    f"""
                    <div class="event-item {css_class}">
                        <div style="display:flex;justify-content:space-between;align-items:start;">
                            <span style="font-weight:600;font-size:0.85rem;color:#f1f5f9;">
                                {event.get('region','Unknown')} — {event.get('disruption_type','').replace('_',' ').title()}
                            </span>
                            {risk_badge(sev)}
                        </div>
                        <p style="margin:4px 0 2px 0;font-size:0.8rem;color:#94a3b8;">
                            {event.get('summary','No summary available.')[:200]}
                        </p>
                        <div style="font-size:0.72rem;color:#475569;">
                            ⚡ SDI: <b>{float(event.get('sdi_score') or 0.0):.1f}</b> &nbsp;|&nbsp;
                            🎯 Confidence: <b>{float(event.get('confidence') or 0.0):.0%}</b> &nbsp;|&nbsp;
                            🚢 {chokepoints} &nbsp;|&nbsp; {ts_str}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)

    with col_chart:
        st.markdown("#### 📉 SDI Score Timeline")

        if events:
            ts_list, sdi_list = [], []
            for e in reversed(events):
                ts_raw = e.get("created_at")
                if ts_raw:
                    ts_list.append(pd.to_datetime(ts_raw, utc=True))
                    sdi_list.append(float(e.get("sdi_score") or 0.0))

            if ts_list:
                fig_sdi = go.Figure()
                fig_sdi.add_trace(go.Scatter(
                    x=ts_list, y=sdi_list,
                    mode="lines+markers",
                    name="SDI",
                    line=dict(color="#3b82f6", width=2.5, shape="spline"),
                    marker=dict(size=6, color="#06b6d4"),
                    fill="tozeroy",
                    fillcolor="rgba(59,130,246,0.1)",
                ))
                fig_sdi.add_hline(y=75, line_dash="dash", line_color="#ef4444",
                                  annotation_text="Critical (75)", annotation_position="right")
                fig_sdi.add_hline(y=50, line_dash="dash", line_color="#f97316",
                                  annotation_text="High (50)", annotation_position="right")
                fig_sdi.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#94a3b8", size=11),
                    margin=dict(l=0, r=60, t=20, b=0),
                    height=320,
                    showlegend=False,
                    yaxis=dict(range=[0, 100], gridcolor="rgba(255,255,255,0.05)"),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                )
                st.plotly_chart(fig_sdi, use_container_width=True)
        else:
            st.info("SDI timeline will populate once the cron worker runs its first cycle.")

        # Chokepoint risk matrix
        st.markdown("#### ⚠️ Chokepoint Risk Matrix")
        matrix = cached_chokepoint_matrix()
        if matrix:
            df_matrix = pd.DataFrame(matrix)
            df_matrix = df_matrix.rename(columns={
                "name": "Chokepoint", "flow_mb_day": "Flow (Mb/d)",
                "risk_score": "Risk Score", "sdi_contribution": "SDI Contrib.",
                "vessels_current": "Vessels", "price_impact_usd": "Price Impact $"
            })
            display_cols = ["Chokepoint", "Flow (Mb/d)", "Risk Score", "SDI Contrib.", "Vessels", "Price Impact $"]
            st.dataframe(df_matrix[[c for c in display_cols if c in df_matrix.columns]],
                         use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — MARKET PULSE
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.markdown("#### Energy Market Price Dashboard")

    prices_raw = cached_prices(days=60)

    ticker_labels = {
        "BZ=F": "🛢️ Brent Crude (USD/bbl)",
        "NG=F": "🔥 Natural Gas (USD/MMBtu)",
        "USO":  "📊 USO ETF",
        "XLE":  "⚡ XLE Energy ETF",
    }

    selected_ticker = st.radio(
        "Select Instrument",
        options=list(ticker_labels.keys()),
        format_func=lambda t: ticker_labels[t],
        horizontal=True,
    )

    price_df = format_price_chart_df(prices_raw, selected_ticker)

    if price_df.empty:
        st.info("Price data not yet available. Run `python cron_worker.py --once` to fetch initial data.")
    else:
        # Candlestick chart
        fig_candle = go.Figure()

        if all(c in price_df.columns for c in ["open", "high", "low", "close"]):
            fig_candle.add_trace(go.Candlestick(
                x=price_df["date"],
                open=price_df["open"],
                high=price_df["high"],
                low=price_df["low"],
                close=price_df["close"],
                name=selected_ticker,
                increasing_line_color="#22c55e",
                decreasing_line_color="#ef4444",
                increasing_fillcolor="rgba(34,197,94,0.3)",
                decreasing_fillcolor="rgba(239,68,68,0.3)",
            ))

        # 7-day MA overlay
        if len(price_df) >= 7:
            price_df["ma7"] = price_df["close"].rolling(7).mean()
            fig_candle.add_trace(go.Scatter(
                x=price_df["date"], y=price_df["ma7"],
                name="7-day MA",
                line=dict(color="#3b82f6", width=1.5, dash="dot"),
            ))

        fig_candle.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", size=11),
            margin=dict(l=0, r=0, t=30, b=0),
            height=380,
            legend=dict(
                orientation="h", bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94a3b8"),
            ),
            xaxis=dict(
                gridcolor="rgba(255,255,255,0.04)",
                rangeslider=dict(visible=False),
            ),
            yaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
            title=dict(text=ticker_labels[selected_ticker], font=dict(color="#e2e8f0", size=13)),
        )
        st.plotly_chart(fig_candle, use_container_width=True)

        # Summary stats
        latest  = price_df["close"].iloc[-1]
        prev    = price_df["close"].iloc[-2] if len(price_df) > 1 else latest
        chg     = latest - prev
        chg_pct = (chg / prev * 100) if prev != 0 else 0

        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Current", f"${latest:.2f}", f"{chg:+.2f} ({chg_pct:+.2f}%)")
        sc2.metric("60d High", f"${price_df['high'].max():.2f}" if "high" in price_df.columns else "—")
        sc3.metric("60d Low",  f"${price_df['low'].min():.2f}"  if "low" in price_df.columns else "—")
        sc4.metric("Avg Volume", f"{int(price_df['volume'].mean()):,}" if "volume" in price_df.columns else "—")

    # All-ticker summary table
    st.markdown("#### All Energy Instruments — Latest Close")
    summary_rows = []
    for t in ["BZ=F", "NG=F", "USO", "XLE"]:
        df_t = format_price_chart_df(prices_raw, t)
        if not df_t.empty:
            summary_rows.append({
                "Instrument": ticker_labels[t],
                "Last Close":  f"${df_t['close'].iloc[-1]:.2f}",
                "Change":      f"{df_t['close'].iloc[-1] - df_t['close'].iloc[-2]:+.2f}"
                               if len(df_t) > 1 else "—",
                "Date":        str(df_t["date"].iloc[-1].date()),
            })
    if summary_rows:
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — REROUTE MATRIX
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    st.markdown("#### 🔀 Adaptive Procurement Orchestrator — Reroute Analysis Engine")
    st.markdown(
        "<p style='color:#64748b;font-size:0.85rem;'>5-step algorithm: chemical constraint → spatial traversal → "
        "VLCC freight math → lead time → ranked procurement matrix. Zero hallucinations — "
        "Neo4j + PostgreSQL only.</p>",
        unsafe_allow_html=True,
    )

    col_sel1, col_sel2, col_sel3 = st.columns([2, 2, 1])

    with col_sel1:
        chokepoint_options = cached_chokepoints()
        selected_chokepoint = st.selectbox(
            "🚫 Blocked Chokepoint",
            options=chokepoint_options,
            index=0,
        )

    with col_sel2:
        crude_grade_options = ["Any Grade"] + get_crude_grade_list()
        selected_crude = st.selectbox(
            "🛢️ Crude Grade Required",
            options=crude_grade_options,
        )

    with col_sel3:
        ranking_mode = st.radio(
            "Rank by",
            options=["cost", "speed"],
            format_func=lambda x: "💰 Cost" if x == "cost" else "⚡ Speed",
            horizontal=False,
        )

    # Destination refinery row
    dest_col1, dest_col2 = st.columns([3, 1])
    with dest_col1:
        refinery_options = cached_refinery_list()
        # Default to Jamnagar (largest refinery, first in capacity-sorted list)
        default_idx = next(
            (i for i, r in enumerate(refinery_options) if "Jamnagar" in r), 0
        )
        selected_dest_label = st.selectbox(
            "🏭 Destination Refinery",
            options=refinery_options,
            index=default_idx,
            help="Select the target refinery. Lead times are calculated using real great-circle distances from each export terminal to this location.",
        )
        # Strip the (Country) suffix to get the bare refinery name
        selected_dest = selected_dest_label.rsplit(" (", 1)[0]

    run_analysis = st.button("⚡ Generate Reroute Matrix", use_container_width=True, type="primary")

    if run_analysis:
        grade = None if selected_crude == "Any Grade" else selected_crude

        with st.spinner(f"Running 5-step procurement analysis for {selected_chokepoint} → {selected_dest} ..."):
            result = find_alternatives(
                blocked_chokepoint=selected_chokepoint,
                crude_grade=grade,
                ranking_mode=ranking_mode,
                destination_refinery=selected_dest,
            )

        st.markdown("---")

        # ── Header KPIs ─────────────────────────────────────────────────────
        res_score = result["resilience_score"]
        pm        = result["procurement_matrix"]
        brent     = result["current_brent_usd"]
        fparams   = result["freight_params"]

        h1, h2, h3, h4 = st.columns(4)
        h1.metric("🛡️ Resilience Index",  f"{res_score:.1f} / 100")
        h2.metric("💲 Brent Spot",        f"${brent:.2f} /bbl")
        h3.metric("🚢 Viable Sources",    len(pm))
        h4.metric("🏭 Destination",       result.get("destination_refinery", selected_dest))

        st.markdown("---")

        # ── Procurement Matrix ───────────────────────────────────────────────
        if pm:
            grade_note = (
                f"Chemically filtered for **{grade}** (API gravity matched)" if result["grade_filtered"]
                else "_Grade constraint widened — no exact match found for blocked region_"
            )
            st.markdown(f"##### 📋 Ranked Procurement Matrix   ·   {grade_note}")

            df_pm = pd.DataFrame(pm)

            # Rename columns for display
            rename_pm = {
                "export_port":       "Export Terminal",
                "country":           "Country",
                "crude_grade":       "Crude Grade",
                "brent_spot_usd":    "Brent ($/bbl)",
                "freight_premium":   "Freight Premium ($/bbl)",
                "landed_cost_usd":   "Landed Cost ($/bbl)",
                "lead_time_days":    "Lead Time (days)",
                "risk_score":        "Route Risk",
                "composite_score":   "Score",
                "recommended":       "✅ Top Pick",
            }
            display_cols = ["export_port", "country", "crude_grade",
                            "landed_cost_usd", "freight_premium",
                            "lead_time_days", "risk_score", "composite_score", "recommended"]
            df_disp = df_pm[[c for c in display_cols if c in df_pm.columns]].copy()
            df_disp = df_disp.rename(columns={k: v for k, v in rename_pm.items() if k in df_disp.columns})

            # Format numbers
            for col in ["Brent ($/bbl)", "Freight Premium ($/bbl)", "Landed Cost ($/bbl)"]:
                if col in df_disp.columns:
                    df_disp[col] = df_disp[col].apply(lambda v: f"${v:.2f}")
            if "Lead Time (days)" in df_disp.columns:
                df_disp["Lead Time (days)"] = df_disp["Lead Time (days)"].apply(lambda v: f"{v:.1f}")
            if "Route Risk" in df_disp.columns:
                df_disp["Route Risk"] = df_disp["Route Risk"].apply(lambda v: f"{v:.0%}")
            if "Score" in df_disp.columns:
                df_disp["Score"] = df_disp["Score"].apply(lambda v: f"{v:.3f}")
            if "✅ Top Pick" in df_disp.columns:
                df_disp["✅ Top Pick"] = df_disp["✅ Top Pick"].apply(lambda v: "✅ YES" if v else "")

            st.dataframe(df_disp, use_container_width=True, hide_index=True)

            # ── Top recommendation callout ────────────────────────────────
            top = pm[0]
            st.markdown(
                f'<div style="background:linear-gradient(135deg,rgba(34,197,94,0.15),rgba(34,197,94,0.05));'
                f'border:1px solid rgba(34,197,94,0.35);border-radius:10px;padding:1rem;margin-top:0.75rem;">'
                f'<span style="color:#22c55e;font-weight:700;font-size:1rem;">✅ Top Recommendation</span><br/>'
                f'<span style="color:#f1f5f9;font-size:0.9rem;">'
                f'<b>{top["export_port"]}</b> ({top["country"]}) · '
                f'<b>{top["crude_grade"]}</b> · '
                f'Landed Cost: <b>${top["landed_cost_usd"]:.2f}/bbl</b> · '
                f'Lead Time: <b>{top["lead_time_days"]:.1f} days</b>'
                f'</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Freight Premium Breakdown ─────────────────────────────────
            with st.expander("📊 Freight Premium Calculation Breakdown"):
                dest_disp = result.get("destination_refinery", selected_dest)
                dest_c    = result.get("dest_coords", {})
                dest_loc  = f"({dest_c.get('lat', '?'):.2f}°, {dest_c.get('lon', '?'):.2f}°)" if dest_c else ""
                st.markdown(f"""
| Parameter | Value |
|---|---|
| **Destination Refinery** | **{dest_disp}** {dest_loc} |
| Distance Method | Marine routing (searoute) |
| VLCC Daily Charter Rate | ${fparams['vlcc_daily_charter_usd']:,} /day |
| VLCC Cargo Capacity | {fparams['vlcc_cargo_barrels']:,} barrels |
| VLCC Average Speed | {fparams['vlcc_speed_knots']} knots ({fparams['vlcc_speed_knots'] * 24:.0f} NM/day) |
| **Freight Premium per bbl** | **Variable by Port** (conditionally applied based on transit) |
| **Brent Spot** | **${brent:.2f} /bbl** |

> Formula: `Landed Cost = Brent Spot + (Charter Rate × Conditional Detour Days) / Cargo Barrels`
> Lead Time: `searoute(port → {dest_disp}) / (13 knots × 24h) + conditional detour days`
                """)
        else:
            st.warning(
                f"No viable procurement sources found bypassing **{selected_chokepoint}**. "
                "This may indicate a global supply shock scenario. Consider widening the grade constraint."
            )

        # ── Refinery Compatibility ────────────────────────────────────────
        if result["refinery_options"]:
            st.markdown(f"---")
            st.markdown(f"#### 🏭 Refineries Compatible with **{selected_crude}**")
            df_ref = pd.DataFrame(result["refinery_options"])
            rename_ref = {
                "refinery":     "Refinery",
                "country":      "Country",
                "capacity_kbd": "Capacity (kbd)",
            }
            df_ref = df_ref.rename(columns={k: v for k, v in rename_ref.items() if k in df_ref.columns})
            st.dataframe(df_ref, use_container_width=True, hide_index=True)

        # ── Related Risk Events ───────────────────────────────────────────
        if result["context_events"]:
            st.markdown("---")
            st.markdown("#### 📰 Related Intelligence Events")
            for ev in result["context_events"][:3]:
                sev = float(ev.get("severity", 0))
                css_class = "high" if sev >= 0.7 else "medium" if sev >= 0.4 else "low"
                st.markdown(
                    f'<div class="event-item {css_class}">'
                    f'<b>{ev.get("disruption_type","").replace("_"," ").title()}</b> — '
                    f'{ev.get("region","")}<br/>'
                    f'<span style="font-size:0.8rem;color:#94a3b8;">{ev.get("summary","")[:150]}...</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    else:
        st.markdown(
            '<div class="info-card">'
            '<p style="color:#94a3b8;margin:0;">👆 Select a blocked chokepoint and crude grade above, then click '
            '<b>Generate Reroute Matrix</b> to run the full 5-step procurement analysis.</p>'
            '</div>',
            unsafe_allow_html=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — SPR OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════

with tab5:
    st.markdown("#### 🛢️ Strategic Petroleum Reserve (SPR) Burn-Down Simulator")
    st.markdown(
        '<p style="color:#94a3b8;font-size:0.85rem;margin:-0.5rem 0 1rem 0;">'
        'India holds ~39 million barrels across 3 sites — providing ~9.5 days of national cover. '
        'Model the exact day reserves hit zero and the demand management actions needed to survive until the rerouted shipment arrives.'
        '</p>',
        unsafe_allow_html=True,
    )

    spr_c1, spr_c2, spr_c3 = st.columns([2, 2, 1])
    with spr_c1:
        spr_chokepoint = st.selectbox(
            "Blocked Chokepoint",
            options=cached_chokepoints(),
            key="spr_chokepoint",
            help="Which chokepoint is blocked? This determines India's daily import shortfall.",
        )
    with spr_c2:
        spr_lead_time = st.slider(
            "Rerouted Shipment Lead Time (days)",
            min_value=5.0, max_value=60.0, value=22.0, step=0.5,
            key="spr_lead_time",
            help="How many days until the rerouted tanker arrives? Pull this from the Reroute Matrix tab.",
        )
    with spr_c3:
        spr_override = st.number_input(
            "Override Shortfall (mbpd)",
            min_value=0.0, max_value=5.4, value=0.0, step=0.1,
            key="spr_override",
            help="Optional: manually set the daily disruption volume. 0 = auto-calculate from chokepoint share.",
        )

    run_spr = st.button("🔬 Run SPR Simulation", use_container_width=True, type="primary", key="run_spr")

    if run_spr:
        override_vol = spr_override if spr_override > 0 else None
        with st.spinner("Simulating SPR burn-down..."):
            spr = calculate_spr_impact(
                lead_time_days=spr_lead_time,
                blocked_chokepoint=spr_chokepoint,
                disrupted_volume_mbpd=override_vol,
            )

        st.markdown("---")

        # ── KPI Row ─────────────────────────────────────────────────────────
        gap_color = "#ef4444" if spr["supply_gap_days"] > 0 else "#22c55e"
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("Daily Shortfall",   f"{spr['daily_shortfall_mbpd']:.2f} mbpd")
        s2.metric("SPR Survival Days", f"{spr['survival_days']:.1f} days",
                  delta=f"{spr['survival_days'] - spr_lead_time:.1f} vs lead time",
                  delta_color="normal" if spr['survival_days'] >= spr_lead_time else "inverse")
        s3.metric("Supply Gap",        f"{spr['supply_gap_days']:.1f} days",
                  delta="Gap after SPR" if spr['supply_gap_days'] > 0 else "No gap",
                  delta_color="inverse" if spr['supply_gap_days'] > 0 else "normal")
        s4.metric("GDP Impact (est)",  spr["macro_gdp_impact_pct"],
                  delta=spr["macro_gdp_impact_usd"], delta_color="inverse")
        s5.metric("Inflation Impact",  spr["macro_infl_impact"], delta_color="inverse")

        # ── Recommendation Banner ────────────────────────────────────────────
        bg_color = {
            "green":  "rgba(34,197,94,0.15)",
            "orange": "rgba(249,115,22,0.15)",
            "red":    "rgba(239,68,68,0.15)",
        }.get(spr["status_color"], "rgba(100,100,100,0.1)")
        border_color = {
            "green":  "rgba(34,197,94,0.4)",
            "orange": "rgba(249,115,22,0.4)",
            "red":    "rgba(239,68,68,0.4)",
        }.get(spr["status_color"], "rgba(100,100,100,0.3)")
        st.markdown(
            f'<div style="background:{bg_color};border:1px solid {border_color};'
            f'border-radius:10px;padding:1rem;margin:0.75rem 0;">'
            f'<span style="font-size:1.05rem;font-weight:700;">{spr["recommendation"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Burn-Down Chart ──────────────────────────────────────────────────
        st.markdown("##### 📉 SPR Burn-Down Trajectory")
        df_bd = spr["burndown_df"]

        fig_spr = go.Figure()

        # Capacity ceiling
        fig_spr.add_trace(go.Scatter(
            x=df_bd["Day"], y=df_bd["SPR Capacity (MB)"],
            mode="lines", name="Full Capacity",
            line=dict(color="rgba(100,116,139,0.4)", dash="dot", width=1),
        ))

        # Safe floor (10% emergency buffer)
        fig_spr.add_trace(go.Scatter(
            x=df_bd["Day"], y=df_bd["Safe Floor (MB)"],
            mode="lines", name="Emergency Floor (10%)",
            line=dict(color="rgba(239,68,68,0.5)", dash="dash", width=1.5),
            fill=None,
        ))

        # Managed scenario
        fig_spr.add_trace(go.Scatter(
            x=df_bd["Day"], y=df_bd["SPR Managed (MB)"],
            mode="lines", name="With Demand Management",
            line=dict(color="#f59e0b", width=2.5, shape="spline"),
            fill="tonexty",
            fillcolor="rgba(245,158,11,0.06)",
        ))

        # Baseline burn
        fig_spr.add_trace(go.Scatter(
            x=df_bd["Day"], y=df_bd["SPR Level (MB)"],
            mode="lines", name="Baseline (No Intervention)",
            line=dict(color="#ef4444", width=3, shape="spline"),
            fill="tozeroy",
            fillcolor="rgba(239,68,68,0.08)",
        ))

        # Ships arrive vertical line
        fig_spr.add_vline(
            x=int(spr_lead_time),
            line_dash="dash", line_color="#22c55e", line_width=2,
            annotation_text=f"🚢 Ships Arrive (Day {int(spr_lead_time)})",
            annotation_position="top right",
            annotation_font_color="#22c55e",
        )

        # SPR zero line
        if spr["supply_gap_days"] > 0:
            fig_spr.add_hline(
                y=0, line_color="rgba(239,68,68,0.8)", line_width=1,
                annotation_text="⚠️ ZERO OIL",
                annotation_position="right",
                annotation_font_color="#ef4444",
            )

        fig_spr.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(15,20,40,0.6)",
            height=380,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(title="Days Since Disruption", gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(title="SPR Level (Million Barrels)", gridcolor="rgba(255,255,255,0.05)"),
            margin=dict(l=40, r=40, t=40, b=40),
        )
        st.plotly_chart(fig_spr, use_container_width=True)

        # ── Two-Column Detail ────────────────────────────────────────────────
        col_dm, col_sites = st.columns([3, 2])

        with col_dm:
            st.markdown("##### 🎛️ Demand Management Playbook")
            if spr["demand_actions"]:
                df_da = pd.DataFrame(spr["demand_actions"])
                df_da.columns = ["Action", "Impact", "Saves (mbpd)", "Cost"]
                st.dataframe(df_da, use_container_width=True, hide_index=True)
                if spr["adjusted_gap_days"] < spr["supply_gap_days"] and spr["adjusted_gap_days"] > 0:
                    st.markdown(
                        f'<div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);'
                        f'border-radius:8px;padding:0.75rem;margin-top:0.5rem;font-size:0.85rem;">'
                        f'⚡ With all levers applied, the survival gap reduces from '
                        f'<b>{spr["supply_gap_days"]:.1f}</b> days to '
                        f'<b>{spr["adjusted_gap_days"]:.1f}</b> days. '
                        f'GDP impact reduces to <b>{spr["macro_gdp_adj"]}</b>.'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                elif spr["adjusted_gap_days"] == 0 and spr["supply_gap_days"] > 0:
                    st.markdown(
                        f'<div style="background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);'
                        f'border-radius:8px;padding:0.75rem;margin-top:0.5rem;font-size:0.85rem;">'
                        f'✅ Demand levers are sufficient to bridge the full {spr["supply_gap_days"]:.1f}-day gap. '
                        f'GDP impact with management: <b>{spr["macro_gdp_adj"]}</b>.'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<div style="color:#22c55e;padding:0.5rem;">'
                    '✅ SPR coverage is sufficient — no demand management protocols required.'
                    '</div>',
                    unsafe_allow_html=True,
                )

        with col_sites:
            st.markdown("##### 🏭 SPR Sites Status")
            total_days_cover = SPR_CAPACITY_MB / spr["daily_shortfall_mbpd"] if spr["daily_shortfall_mbpd"] > 0 else 999
            for site, capacity in spr["spr_sites"].items():
                site_days = capacity / spr["daily_shortfall_mbpd"] if spr["daily_shortfall_mbpd"] > 0 else 999
                pct_of_total = capacity / SPR_CAPACITY_MB
                fill_color = "#22c55e" if site_days >= spr_lead_time else ("#f59e0b" if site_days >= spr_lead_time * 0.5 else "#ef4444")
                st.markdown(
                    f'<div style="background:rgba(15,23,42,0.8);border:1px solid rgba(51,65,85,0.5);'
                    f'border-radius:8px;padding:0.75rem;margin-bottom:0.5rem;">'
                    f'<div style="font-weight:600;color:#f1f5f9;">{site}</div>'
                    f'<div style="font-size:0.8rem;color:#94a3b8;">'
                    f'{capacity:.1f} MB · Covers {site_days:.1f} days of deficit</div>'
                    f'<div style="margin-top:0.4rem;background:rgba(30,41,59,0.8);border-radius:4px;height:6px;">'
                    f'<div style="width:{pct_of_total:.0%};background:{fill_color};height:6px;border-radius:4px;"></div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                f'<div style="font-size:0.78rem;color:#64748b;margin-top:0.5rem;">'
                f'Total: {SPR_CAPACITY_MB:.0f} MB · {total_days_cover:.1f} days cover at {spr["daily_shortfall_mbpd"]:.2f} mbpd deficit'
                f'</div>',
                unsafe_allow_html=True,
            )

    else:
        st.markdown(
            '<div class="info-card">'
            '<p style="color:#94a3b8;margin:0;">'
            '🛢️ Select a blocked chokepoint and set the rerouted shipment lead time from the '
            '<b>Reroute Matrix</b> tab, then click <b>Run SPR Simulation</b> to model India\'s '
            'petroleum reserve depletion trajectory and recommended policy actions.'
            '</p></div>',
            unsafe_allow_html=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — WAR ROOM (Scenario Simulator & Executive Briefing)
# ══════════════════════════════════════════════════════════════════════════════

with tab6:
    st.markdown("#### ⚔️ Crisis Simulation & Executive Briefing")
    st.markdown(
        '<p style="color:#94a3b8;font-size:0.85rem;margin:-0.5rem 0 1rem 0;">'
        'Run predefined macro-economic crisis scenarios. The AI pipeline will automatically route the ships, calculate the SPR burn-down, and generate a boardroom-ready Emergency Action Plan.'
        '</p>',
        unsafe_allow_html=True,
    )

    war_c1, war_c2 = st.columns([2, 1])
    with war_c1:
        scenario = st.selectbox(
            "Select Crisis Scenario",
            [
                "Scenario A: Complete Hormuz Blockade (2.5 mbpd loss)",
                "Scenario B: Suez Canal Drone Strikes (1.2 mbpd loss)",
                "Scenario C: Malacca Strait Piracy Surge (0.8 mbpd loss)"
            ],
            key="war_scenario"
        )
    with war_c2:
        war_dest = st.selectbox(
            "Target Refinery",
            options=cached_refinery_list(),
            index=0,
            key="war_dest"
        )
        war_dest = war_dest.rsplit(" (", 1)[0]

    if "Hormuz" in scenario:
        war_chokepoint = "Strait of Hormuz"
        war_shortfall = 2.5
    elif "Suez" in scenario:
        war_chokepoint = "Suez Canal"
        war_shortfall = 1.2
    else:
        war_chokepoint = "Strait of Malacca"
        war_shortfall = 0.8

    run_war = st.button("🚨 SIMULATE SCENARIO", use_container_width=True, type="primary", key="run_war")

    if run_war:
        # Step 1: Run Reroute Matrix
        with st.spinner(f"Simulating blockade at {war_chokepoint}..."):
            fixer_result = find_alternatives(
                blocked_chokepoint=war_chokepoint,
                crude_grade=None, # any grade
                ranking_mode="cost",
                destination_refinery=war_dest,
            )
            pm = fixer_result.get("procurement_matrix", [])
            df_pm = pd.DataFrame(pm)

        if not pm:
            st.error("No viable alternative routes found in the graph database for this scenario.")
        else:
            top_route = df_pm.iloc[0]
            lead_time = float(top_route["lead_time_days"])

            # Step 2: Run SPR Modeler
            with st.spinner(f"Calculating SPR burn-down (Shortfall: {war_shortfall} mbpd, Lead Time: {lead_time} days)..."):
                spr = calculate_spr_impact(
                    lead_time_days=lead_time,
                    blocked_chokepoint=war_chokepoint,
                    disrupted_volume_mbpd=war_shortfall,
                )

            # Layout Results
            st.markdown("---")
            st.markdown("##### 1. Optimal Reroute Strategy")
            
            # Format PM for display
            rename_pm = {
                "export_port":       "Export Terminal",
                "crude_grade":       "Crude Grade",
                "landed_cost_usd":   "Landed Cost ($/bbl)",
                "lead_time_days":    "Lead Time (days)",
            }
            display_cols = ["export_port", "crude_grade", "landed_cost_usd", "lead_time_days"]
            df_disp = df_pm[[c for c in display_cols if c in df_pm.columns]].copy().head(3)
            df_disp = df_disp.rename(columns={k: v for k, v in rename_pm.items() if k in df_disp.columns})
            df_disp["Landed Cost ($/bbl)"] = df_disp["Landed Cost ($/bbl)"].apply(lambda v: f"${v:.2f}")
            df_disp["Lead Time (days)"] = df_disp["Lead Time (days)"].apply(lambda v: f"{v:.1f}")
            st.dataframe(df_disp, use_container_width=True, hide_index=True)

            st.markdown("##### 2. SPR Trajectory")
            s1, s2, s3 = st.columns(3)
            s1.metric("SPR Survival Days", f"{spr['survival_days']:.1f} days")
            s2.metric("Supply Gap", f"{spr['supply_gap_days']:.1f} days", delta="CRITICAL" if spr['supply_gap_days'] > 0 else "SAFE", delta_color="inverse")
            s3.metric("GDP Impact (Est)", spr["macro_gdp_impact_pct"])

            st.markdown("---")
            st.markdown("##### 3. Ministry of Petroleum Executive Brief")
            
            # Step 3: Run Briefing Agent
            with st.spinner("Generating LLM Executive Action Plan..."):
                brief_text = generate_emergency_brief(
                    scenario_name=scenario,
                    target_refinery=war_dest,
                    spr_data=spr,
                    reroute_df=df_disp,
                )
            
            st.info(brief_text, icon="📄")

# ---------------------------------------------------------------------------
# Auto-Refresh Footer
# ---------------------------------------------------------------------------

st.divider()
footer_col1, footer_col2 = st.columns([3, 1])
footer_col1.markdown(
    f'<p style="color:#334155;font-size:0.75rem;">Shadow Cache | Local PostgreSQL + Neo4j | Gemini 2.0 Flash | '
    f'Refreshed: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</p>',
    unsafe_allow_html=True,
)

if auto_refresh:
    time.sleep(60)
    st.rerun()
