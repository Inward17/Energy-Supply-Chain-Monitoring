"""
src/ingestion/ais_streamer.py
──────────────────────────────
AISStream.io WebSocket collector for live vessel telemetry.

Connects to wss://stream.aisstream.io/v0/stream and collects position
reports for tankers transiting strategic energy chokepoints.

Strategy (Shadow Cache compatible):
  - Runs for a configurable snapshot window (default 120 seconds) per cron cycle.
  - Stores vessel positions to vessel_telemetry; does NOT hold a persistent socket.
  - Filtered to 6 high-priority bounding boxes covering 90% of global oil transit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import websockets
from dotenv import load_dotenv

from src.database.postgres_db import (
    upsert_vessel,
    fetch_vessel_types,
    upsert_vessel_types,
)

load_dotenv()
logger = logging.getLogger(__name__)

AISSTREAM_URI = "wss://stream.aisstream.io/v0/stream"

# AIS broadcasts position reports every few seconds but ship *type* only in
# Type-5 (ShipStaticData) messages, roughly every 6 minutes. A snapshot shorter
# than that period types only ~window/360 of the vessels it sees, which is why
# 120s yielded ~33% type coverage and left the SDI vessel-density term (25% of
# the index) permanently disabled by its 70%-coverage gate. Types are persisted
# to vessel_type_registry, so coverage compounds across cycles.
DEFAULT_SNAPSHOT_SECONDS = 600
AIS_STATIC_BROADCAST_PERIOD_SECONDS = 360

# ---------------------------------------------------------------------------
# Bounding Boxes for Strategic Chokepoints
# ---------------------------------------------------------------------------
# Format: [[min_lat, min_lon], [max_lat, max_lon]]

STRATEGIC_BOUNDING_BOXES = [
    # Strait of Hormuz + Persian Gulf outlet
    [[23.0, 55.0], [28.0, 59.0]],
    # Red Sea + Bab-el-Mandeb
    [[11.0, 41.0], [15.0, 46.0]],
    # Suez Canal approaches
    [[28.0, 31.0], [32.0, 34.0]],
    # Strait of Malacca
    [[-2.0, 100.0], [6.0, 106.0]],
    # Turkish Straits (Bosphorus)
    [[40.5, 28.5], [41.5, 30.0]],
    # Cape of Good Hope approaches
    [[-36.0, 17.0], [-32.0, 21.0]],
]

REGION_LABELS = {
    0: "Strait of Hormuz",
    1: "Bab-el-Mandeb",
    2: "Suez Canal",
    3: "Strait of Malacca",
    4: "Turkish Straits",
    5: "Cape of Good Hope",
}


def _label_region(lat: float, lon: float) -> str:
    """Assign a region label based on lat/lon coordinates."""
    for idx, bbox in enumerate(STRATEGIC_BOUNDING_BOXES):
        min_lat, min_lon = bbox[0]
        max_lat, max_lon = bbox[1]
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return REGION_LABELS.get(idx, "Unknown")
    return "Unknown"


# ---------------------------------------------------------------------------
# Async Collection
# ---------------------------------------------------------------------------

async def _stream_snapshot(
    api_key: str,
    duration_seconds: int,
    buffer: list[dict[str, Any]],
    ship_types_cache: dict[int, int],
    new_ship_types: list[dict[str, Any]],
) -> None:
    """
    Open a WebSocket connection, collect vessel positions for `duration_seconds`,
    then close the connection cleanly.

    Args:
        api_key:          AISStream API key.
        duration_seconds: How long to keep the connection open.
        buffer:           List to append parsed vessel records into.
    """
    subscribe_msg = json.dumps({
        "APIKey":           api_key,
        "BoundingBoxes":    STRATEGIC_BOUNDING_BOXES,
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
    })

    deadline = asyncio.get_event_loop().time() + duration_seconds

    try:
        async with websockets.connect(AISSTREAM_URI, ping_interval=20, ping_timeout=10) as ws:
            await ws.send(subscribe_msg)
            logger.info("AISStream connected — collecting for %ds ...", duration_seconds)

            async for raw_msg in ws:
                if asyncio.get_event_loop().time() >= deadline:
                    logger.info("AISStream snapshot window elapsed. Disconnecting.")
                    break

                try:
                    msg = json.loads(raw_msg)
                    mtype = msg.get("MessageType", "")

                    if mtype == "PositionReport":
                        pos = msg["Message"]["PositionReport"]
                        meta = msg.get("MetaData", {})
                        lat = pos.get("Latitude", 0.0)
                        lon = pos.get("Longitude", 0.0)

                        # Filter garbage coordinates
                        if lat == 0.0 and lon == 0.0:
                            continue
                        if abs(lat) > 90 or abs(lon) > 180:
                            continue

                        buffer.append({
                            "mmsi":        pos.get("UserID"),
                            "vessel_name": meta.get("ShipName", "").strip() or "Unknown",
                            "lat":         round(lat, 5),
                            "lon":         round(lon, 5),
                            "speed":       round(pos.get("Sog", 0.0), 1),
                            "heading":     pos.get("TrueHeading", 0),
                            "region":      _label_region(lat, lon),
                            "recorded_at": datetime.now(timezone.utc),
                        })

                    elif mtype == "ShipStaticData":
                        static = msg["Message"]["ShipStaticData"]
                        mmsi = static.get("UserID")
                        ship_type = static.get("Type")
                        if mmsi and ship_type is not None:
                            if ship_types_cache.get(mmsi) != ship_type:
                                ship_types_cache[mmsi] = ship_type
                                new_ship_types.append({
                                    "mmsi": mmsi,
                                    "ship_type": ship_type,
                                    "first_seen": datetime.now(timezone.utc)
                                })

                except (KeyError, json.JSONDecodeError):
                    continue

    except websockets.exceptions.InvalidURI:
        logger.error("AISStream: invalid URI. Check AISSTREAM_API_KEY.")
    except websockets.exceptions.WebSocketException as exc:
        logger.error("AISStream WebSocket error: %s", exc)
    except asyncio.TimeoutError:
        logger.warning("AISStream: connection timed out.")


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def snapshot_vessels(duration_seconds: int | None = None) -> int:
    """
    Collect a snapshot of vessel positions from AISStream and store to Postgres.

    Args:
        duration_seconds: Override snapshot window; defaults to AIS_SNAPSHOT_SECONDS env var.

    Returns:
        Number of vessel records stored.
    """
    api_key = os.getenv("AISSTREAM_API_KEY", "")
    if not api_key:
        logger.warning("ais_streamer: AISSTREAM_API_KEY not configured — skipping AIS snapshot. "
                       "Threat Map will show last-known seed data positions.")
        return 0

    secs = duration_seconds or int(os.getenv("AIS_SNAPSHOT_SECONDS", str(DEFAULT_SNAPSHOT_SECONDS)))
    buffer: list[dict[str, Any]] = []
    ship_types_cache = fetch_vessel_types()
    new_ship_types: list[dict[str, Any]] = []

    # The in-loop deadline is only evaluated when a message arrives, so a stalled
    # socket could otherwise block the cron worker for the whole window. Cap it.
    async def _collect() -> None:
        try:
            await asyncio.wait_for(
                _stream_snapshot(api_key, secs, buffer, ship_types_cache, new_ship_types),
                timeout=secs + 30,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "AISStream: snapshot exceeded %ds budget; keeping %d records collected so far.",
                secs + 30,
                len(buffer),
            )

    # Run async collection synchronously
    try:
        asyncio.run(_collect())
    except RuntimeError:
        # Already inside an event loop (e.g. Jupyter); use nest_asyncio or thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_collect())

    if new_ship_types:
        upsert_vessel_types(new_ship_types)
        logger.info("ais_streamer: learned %d new ship types.", len(new_ship_types))

    if not buffer:
        logger.info("AISStream: no vessel records collected in this snapshot.")
        return 0

    # Enrich position reports with latest known ship types
    for rec in buffer:
        rec["ship_type"] = ship_types_cache.get(rec["mmsi"])

    # Type coverage gates the SDI vessel-density term (needs 70%), so log it —
    # a persistently low value means the snapshot window is too short.
    typed = sum(1 for rec in buffer if rec["ship_type"] is not None)
    coverage = typed / len(buffer) if buffer else 0.0

    stored = upsert_vessel(buffer)
    logger.info(
        "ais_streamer: %d vessel records stored (%d collected, %.0f%% ship-type coverage).",
        stored,
        len(buffer),
        coverage * 100,
    )
    if coverage < 0.70:
        logger.warning(
            "ais_streamer: ship-type coverage %.0f%% is below the 70%% gate — the SDI "
            "vessel-density term will stay disabled. Consider raising AIS_SNAPSHOT_SECONDS "
            "(currently %ds; static broadcasts are ~%ds apart).",
            coverage * 100,
            secs,
            AIS_STATIC_BROADCAST_PERIOD_SECONDS,
        )
    return stored


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    n = snapshot_vessels(duration_seconds=30)
    print(f"Stored {n} vessel records.")
