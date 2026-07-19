"""
src/database/neo4j_graph.py
────────────────────────────
Local Neo4j knowledge graph interface for the energy supply chain.

The driver is initialised once at module level. All queries run inside
`with driver.session() as session:` blocks to ensure clean session teardown.

Graph Schema
────────────
Node labels:   Chokepoint | ExportPort | Refinery | CrudeGrade
Relationships:
  (ExportPort)-[:SHIPS_THROUGH]->(Chokepoint)
  (ExportPort)-[:EXPORTS]->(CrudeGrade)
  (Refinery)-[:COMPATIBLE_WITH]->(CrudeGrade)
  (Chokepoint)-[:CONNECTS_TO]->(Chokepoint)

Seed data covers:
  - 8 major maritime chokepoints
  - 12 major global crude export terminals (with transit dependencies)
  - 20 globally significant refineries
  - 17 crude oil grades with API gravity + sulphur specs
"""

from __future__ import annotations

import os
import logging
from typing import Any

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable
from dotenv import load_dotenv
load_dotenv(override=True)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Driver Singleton
# ---------------------------------------------------------------------------

_driver: Driver | None = None


def get_driver() -> Driver | None:
    """Return (or lazily create) the shared Neo4j driver. Returns None if unavailable."""
    global _driver
    if _driver is None:
        uri  = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        pwd  = os.getenv("NEO4J_PASSWORD", "")
        try:
            _driver = GraphDatabase.driver(uri, auth=(user, pwd))
            _driver.verify_connectivity()
            logger.info("Neo4j driver connected to %s", uri)
        except ServiceUnavailable:
            logger.warning("Neo4j unavailable at %s — graph features disabled.", uri)
            _driver = None
    return _driver


def close_driver() -> None:
    """Cleanly close the Neo4j driver (call on application shutdown)."""
    global _driver
    if _driver:
        _driver.close()
        _driver = None


# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------

_CHOKEPOINTS = [
    {"name": "Strait of Hormuz",    "flow_mb_day": 21.0, "lat": 26.56,  "lon": 56.25,  "region": "Middle East"},
    {"name": "Strait of Malacca",   "flow_mb_day": 16.0, "lat": 1.25,   "lon": 103.82, "region": "Southeast Asia"},
    {"name": "Suez Canal",          "flow_mb_day": 9.5,  "lat": 30.58,  "lon": 32.26,  "region": "North Africa"},
    {"name": "Bab-el-Mandeb",       "flow_mb_day": 8.8,  "lat": 12.58,  "lon": 43.41,  "region": "East Africa"},
    {"name": "Cape of Good Hope",   "flow_mb_day": 5.0,  "lat": -34.35, "lon": 18.47,  "region": "Southern Africa"},
    {"name": "Turkish Straits",     "flow_mb_day": 2.9,  "lat": 41.11,  "lon": 29.07,  "region": "Europe"},
    {"name": "Strait of Gibraltar", "flow_mb_day": 1.5,  "lat": 35.98,  "lon": -5.48,  "region": "Mediterranean"},
    {"name": "Panama Canal",        "flow_mb_day": 0.8,  "lat": 9.08,   "lon": -79.68, "region": "Central America"},
]

_CRUDE_GRADES = [
    {"name": "Arab Light",       "api_gravity": 33.4, "sulphur_pct": 1.77, "region": "Middle East"},
    {"name": "Arab Extra Light", "api_gravity": 39.0, "sulphur_pct": 1.15, "region": "Middle East"},
    {"name": "Arab Medium",      "api_gravity": 28.5, "sulphur_pct": 2.59, "region": "Middle East"},
    {"name": "Iranian Heavy",    "api_gravity": 30.9, "sulphur_pct": 1.73, "region": "Middle East"},
    {"name": "Iranian Light",    "api_gravity": 33.8, "sulphur_pct": 1.35, "region": "Middle East"},
    {"name": "Kuwait Export",    "api_gravity": 31.4, "sulphur_pct": 2.52, "region": "Middle East"},
    {"name": "Brent",            "api_gravity": 38.3, "sulphur_pct": 0.37, "region": "North Sea"},
    {"name": "WTI",              "api_gravity": 40.3, "sulphur_pct": 0.24, "region": "North America"},
    {"name": "Urals",            "api_gravity": 31.7, "sulphur_pct": 1.55, "region": "Russia"},
    {"name": "Murban",           "api_gravity": 40.5, "sulphur_pct": 0.78, "region": "UAE"},
    {"name": "Tapis",            "api_gravity": 45.5, "sulphur_pct": 0.04, "region": "Southeast Asia"},
    {"name": "Mexican Maya",     "api_gravity": 22.0, "sulphur_pct": 3.30, "region": "Mexico"},
    {"name": "North Sea Blend",  "api_gravity": 36.0, "sulphur_pct": 0.55, "region": "North Sea"},
    {"name": "Eagle Ford",       "api_gravity": 42.0, "sulphur_pct": 0.10, "region": "North America"},
    {"name": "Russian Sokol",    "api_gravity": 37.4, "sulphur_pct": 0.18, "region": "Russia"},
    {"name": "Duri",             "api_gravity": 20.0, "sulphur_pct": 0.18, "region": "Indonesia"},
    {"name": "Heavy Sour",       "api_gravity": 16.0, "sulphur_pct": 4.50, "region": "Various"},
    {"name": "Bonny Light",      "api_gravity": 33.9, "sulphur_pct": 0.14, "region": "West Africa"},
    {"name": "Escravos",         "api_gravity": 36.4, "sulphur_pct": 0.17, "region": "West Africa"},
    {"name": "Venezuelan Merey", "api_gravity": 16.0, "sulphur_pct": 2.45, "region": "South America"},
]

# Export terminals with their required transit chokepoints and exported grades
# transit_chokepoints: chokepoints a VLCC MUST pass through to leave this port
# available_grades: crude grades exported from this terminal
# baseline_days: approximate baseline voyage days to a typical Asian destination (India)
# lat/lon: terminal coordinates
_EXPORT_PORTS = [
    {
        "name": "Ras Tanura",
        "country": "Saudi Arabia",
        "lat": 26.65, "lon": 50.16,
        "transit_chokepoints": ["Strait of Hormuz"],
        "available_grades": ["Arab Light", "Arab Extra Light", "Arab Medium"],
        "baseline_days_to_india": 10,
    },
    {
        "name": "Mina Al Ahmadi",
        "country": "Kuwait",
        "lat": 29.07, "lon": 48.13,
        "transit_chokepoints": ["Strait of Hormuz"],
        "available_grades": ["Kuwait Export"],
        "baseline_days_to_india": 10,
    },
    {
        "name": "Kharg Island",
        "country": "Iran",
        "lat": 29.23, "lon": 50.33,
        "transit_chokepoints": ["Strait of Hormuz"],
        "available_grades": ["Iranian Heavy", "Iranian Light"],
        "baseline_days_to_india": 10,
    },
    {
        "name": "Basra Oil Terminal",
        "country": "Iraq",
        "lat": 29.68, "lon": 48.83,
        "transit_chokepoints": ["Strait of Hormuz"],
        "available_grades": ["Arab Medium", "Heavy Sour"],
        "baseline_days_to_india": 10,
    },
    {
        "name": "Ruwais Export Terminal",
        "country": "UAE",
        "lat": 24.09, "lon": 52.73,
        "transit_chokepoints": ["Strait of Hormuz"],
        "available_grades": ["Murban", "Arab Light"],
        "baseline_days_to_india": 9,
    },
    {
        "name": "Bonny Export Terminal",
        "country": "Nigeria",
        "lat": 4.45, "lon": 7.15,
        "transit_chokepoints": [],  # Atlantic coast — no major chokepoints for westbound
        "available_grades": ["Bonny Light"],
        "baseline_days_to_india": 22,
    },
    {
        "name": "Escravos Terminal",
        "country": "Nigeria",
        "lat": 5.52, "lon": 5.20,
        "transit_chokepoints": [],
        "available_grades": ["Escravos", "Bonny Light"],
        "baseline_days_to_india": 22,
    },
    {
        "name": "Galveston/Houston",
        "country": "USA",
        "lat": 29.31, "lon": -94.78,
        "transit_chokepoints": ["Panama Canal"],
        "available_grades": ["WTI", "Eagle Ford", "Mexican Maya"],
        "baseline_days_to_india": 30,
    },
    {
        "name": "Sullom Voe",
        "country": "United Kingdom",
        "lat": 60.45, "lon": -1.30,
        "transit_chokepoints": [],
        "available_grades": ["Brent", "North Sea Blend"],
        "baseline_days_to_india": 25,
    },
    {
        "name": "Primorsk",
        "country": "Russia",
        "lat": 60.35, "lon": 28.62,
        "transit_chokepoints": ["Turkish Straits"],
        "available_grades": ["Urals"],
        "baseline_days_to_india": 20,
    },
    {
        "name": "Novorossiysk",
        "country": "Russia",
        "lat": 44.73, "lon": 37.76,
        "transit_chokepoints": ["Turkish Straits"],
        "available_grades": ["Urals", "Russian Sokol"],
        "baseline_days_to_india": 18,
    },
    {
        "name": "Skikda",
        "country": "Algeria",
        "lat": 36.88, "lon": 6.90,
        "transit_chokepoints": ["Strait of Gibraltar"],
        "available_grades": ["North Sea Blend"],
        "baseline_days_to_india": 18,
    },
]

_REFINERIES = [
    {"name": "Jamnagar",              "country": "India",        "capacity_kbd": 1240, "lat": 22.30, "lon": 69.85, "crude_types": ["Arab Light", "Iranian Heavy", "Kuwait Export", "Arab Medium"]},
    {"name": "Rotterdam",             "country": "Netherlands",  "capacity_kbd": 400,  "lat": 51.88, "lon": 4.30,  "crude_types": ["Brent", "Urals", "North Sea Blend"]},
    {"name": "Houston Ship Channel",  "country": "USA",          "capacity_kbd": 600,  "lat": 29.75, "lon": -95.27,"crude_types": ["WTI", "Mexican Maya", "Heavy Sour"]},
    {"name": "Ruwais",                "country": "UAE",          "capacity_kbd": 837,  "lat": 24.09, "lon": 52.73, "crude_types": ["Arab Light", "Murban"]},
    {"name": "Ras Tanura Refinery",   "country": "Saudi Arabia", "capacity_kbd": 550,  "lat": 26.65, "lon": 50.16, "crude_types": ["Arab Light", "Arab Extra Light"]},
    {"name": "Jubail",                "country": "Saudi Arabia", "capacity_kbd": 400,  "lat": 27.01, "lon": 49.66, "crude_types": ["Arab Light"]},
    {"name": "Singapore Jurong",      "country": "Singapore",    "capacity_kbd": 592,  "lat": 1.27,  "lon": 103.70,"crude_types": ["Arab Light", "Tapis", "Duri", "Arab Medium"]},
    {"name": "Ulsan",                 "country": "South Korea",  "capacity_kbd": 840,  "lat": 35.54, "lon": 129.34,"crude_types": ["Arab Light", "Iranian Heavy", "Kuwait Export"]},
    {"name": "Ningbo Zhoushan",       "country": "China",        "capacity_kbd": 400,  "lat": 29.87, "lon": 121.63,"crude_types": ["Arab Medium", "Russian Sokol", "Iranian Heavy"]},
    {"name": "Bandar Abbas",          "country": "Iran",         "capacity_kbd": 280,  "lat": 27.17, "lon": 56.27, "crude_types": ["Iranian Heavy", "Iranian Light"]},
    {"name": "Abadan",                "country": "Iran",         "capacity_kbd": 330,  "lat": 30.34, "lon": 48.30, "crude_types": ["Iranian Light"]},
    {"name": "Leuna",                 "country": "Germany",      "capacity_kbd": 230,  "lat": 51.32, "lon": 12.00, "crude_types": ["Urals"]},
    {"name": "Pernis",                "country": "Netherlands",  "capacity_kbd": 404,  "lat": 51.88, "lon": 4.38,  "crude_types": ["Brent", "Urals", "North Sea Blend"]},
    {"name": "Port Arthur",           "country": "USA",          "capacity_kbd": 635,  "lat": 29.90, "lon": -93.94,"crude_types": ["WTI", "Eagle Ford", "Heavy Sour", "Mexican Maya"]},
    {"name": "Garyville",             "country": "USA",          "capacity_kbd": 578,  "lat": 30.07, "lon": -90.62,"crude_types": ["WTI", "Heavy Sour"]},
    {"name": "Vadinar",               "country": "India",        "capacity_kbd": 400,  "lat": 22.47, "lon": 69.37, "crude_types": ["Arab Light", "Iranian Heavy", "Kuwait Export"]},
    {"name": "Mangalore",             "country": "India",        "capacity_kbd": 300,  "lat": 12.87, "lon": 74.84, "crude_types": ["Arab Light", "Murban"]},
    {"name": "Yanbu",                 "country": "Saudi Arabia", "capacity_kbd": 400,  "lat": 24.09, "lon": 38.07, "crude_types": ["Arab Light", "Arab Extra Light"]},
    {"name": "Shuaiba",               "country": "Kuwait",       "capacity_kbd": 270,  "lat": 29.04, "lon": 48.14, "crude_types": ["Kuwait Export"]},
    {"name": "Mina Al Ahmadi Ref.",   "country": "Kuwait",       "capacity_kbd": 466,  "lat": 29.07, "lon": 48.13, "crude_types": ["Kuwait Export"]},
]


# ---------------------------------------------------------------------------
# Fallback Data (used when Neo4j is not running)
# ---------------------------------------------------------------------------

_FALLBACK_EXPORT_PORTS: dict[str, list[dict]] = {
    "Strait of Hormuz": [
        {"name": "Bonny Export Terminal",  "country": "Nigeria",        "grade": "Bonny Light",   "baseline_days_to_india": 22},
        {"name": "Escravos Terminal",      "country": "Nigeria",        "grade": "Escravos",      "baseline_days_to_india": 22},
        {"name": "Sullom Voe",             "country": "United Kingdom", "grade": "Brent",         "baseline_days_to_india": 25},
        {"name": "Galveston/Houston",      "country": "USA",            "grade": "WTI",           "baseline_days_to_india": 30},
        {"name": "Novorossiysk",           "country": "Russia",         "grade": "Urals",         "baseline_days_to_india": 18},
    ],
    "Suez Canal": [
        {"name": "Ras Tanura",             "country": "Saudi Arabia",   "grade": "Arab Light",    "baseline_days_to_india": 10},
        {"name": "Galveston/Houston",      "country": "USA",            "grade": "WTI",           "baseline_days_to_india": 30},
    ],
    "Bab-el-Mandeb": [
        {"name": "Ras Tanura",             "country": "Saudi Arabia",   "grade": "Arab Light",    "baseline_days_to_india": 10},
        {"name": "Bonny Export Terminal",  "country": "Nigeria",        "grade": "Bonny Light",   "baseline_days_to_india": 22},
    ],
}

_FALLBACK_REFINERY_MATCHES: dict[str, list[dict]] = {
    "Arab Light":    [{"refinery": "Jamnagar (India)",          "capacity_kbd": 1240}],
    "Brent":         [{"refinery": "Rotterdam (Netherlands)",   "capacity_kbd": 400}],
    "WTI":           [{"refinery": "Houston Ship Channel (USA)","capacity_kbd": 600}],
    "Urals":         [{"refinery": "Leuna (Germany)",           "capacity_kbd": 230}],
    "Iranian Heavy": [{"refinery": "Bandar Abbas (Iran)",       "capacity_kbd": 280}],
    "Bonny Light":   [{"refinery": "Jamnagar (India)",          "capacity_kbd": 1240}],
    "Escravos":      [{"refinery": "Singapore Jurong",          "capacity_kbd": 592}],
}

_FALLBACK_ROUTES: dict[str, list[dict]] = {
    "Strait of Hormuz": [
        {"route": "Cape of Good Hope (Africa)", "detour_days": 15, "cost_premium_pct": 22, "risk_score": 0.1},
        {"route": "Trans-Arabian Pipeline (East Med)", "detour_days": 3,  "cost_premium_pct": 8,  "risk_score": 0.15},
    ],
    "Suez Canal": [
        {"route": "Cape of Good Hope (Africa)", "detour_days": 12, "cost_premium_pct": 18, "risk_score": 0.1},
    ],
    "Bab-el-Mandeb": [
        {"route": "Suez Canal → Med bypass", "detour_days": 4, "cost_premium_pct": 10, "risk_score": 0.2},
        {"route": "Cape of Good Hope",       "detour_days": 14,"cost_premium_pct": 20, "risk_score": 0.1},
    ],
    "Strait of Malacca": [
        {"route": "Sunda Strait (Indonesia)", "detour_days": 2, "cost_premium_pct": 5, "risk_score": 0.15},
        {"route": "Lombok Strait (Indonesia)","detour_days": 4, "cost_premium_pct": 8, "risk_score": 0.1},
    ],
}


# ---------------------------------------------------------------------------
# Graph Seeding
# ---------------------------------------------------------------------------

def seed_graph() -> None:
    """
    Idempotently seed the Neo4j knowledge graph.
    Uses MERGE so re-running is safe — no duplicate nodes.
    """
    driver = get_driver()
    if driver is None:
        logger.warning("seed_graph: Neo4j unavailable, skipping.")
        return

    with driver.session() as session:
        # Check if already seeded (look for at least one ExportPort to detect re-seed need)
        ep_count = session.run("MATCH (p:ExportPort) RETURN count(p) AS n").single()["n"]
        node_count = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]

        if ep_count > 0:
            logger.info("Neo4j graph already seeded (%d nodes incl. ExportPorts). Skipping.", node_count)
            return

        if node_count > 0 and ep_count == 0:
            # Old schema — wipe and reseed to add ExportPort nodes
            logger.info("Neo4j has old schema without ExportPorts. Wiping and reseeding...")
            session.run("MATCH (n) DETACH DELETE n")

        logger.info("Seeding Neo4j knowledge graph (chokepoints, export ports, refineries, crude grades)...")

        # Chokepoints
        for cp in _CHOKEPOINTS:
            session.run(
                "MERGE (c:Chokepoint {name: $name}) "
                "SET c.flow_mb_day = $flow, c.lat = $lat, c.lon = $lon, c.region = $region",
                name=cp["name"], flow=cp["flow_mb_day"],
                lat=cp["lat"], lon=cp["lon"], region=cp["region"],
            )

        # Crude grades
        for cg in _CRUDE_GRADES:
            session.run(
                "MERGE (g:CrudeGrade {name: $name}) "
                "SET g.api_gravity = $api, g.sulphur_pct = $sulphur, g.region = $region",
                name=cg["name"], api=cg["api_gravity"],
                sulphur=cg["sulphur_pct"], region=cg["region"],
            )

        # Export Ports + SHIPS_THROUGH + EXPORTS relationships
        for port in _EXPORT_PORTS:
            session.run(
                "MERGE (p:ExportPort {name: $name}) "
                "SET p.country = $country, p.lat = $lat, p.lon = $lon, "
                "    p.baseline_days_to_india = $baseline",
                name=port["name"], country=port["country"],
                lat=port["lat"], lon=port["lon"],
                baseline=port["baseline_days_to_india"],
            )
            for cp_name in port["transit_chokepoints"]:
                session.run(
                    "MATCH (p:ExportPort {name: $pname}), (c:Chokepoint {name: $cname}) "
                    "MERGE (p)-[:SHIPS_THROUGH]->(c)",
                    pname=port["name"], cname=cp_name,
                )
            for grade_name in port["available_grades"]:
                session.run(
                    "MATCH (p:ExportPort {name: $pname}), (g:CrudeGrade {name: $gname}) "
                    "MERGE (p)-[:EXPORTS]->(g)",
                    pname=port["name"], gname=grade_name,
                )

        # Refineries + COMPATIBLE_WITH relationships
        for ref in _REFINERIES:
            session.run(
                "MERGE (r:Refinery {name: $name}) "
                "SET r.country = $country, r.capacity_kbd = $cap, r.lat = $lat, r.lon = $lon",
                name=ref["name"], country=ref["country"], cap=ref["capacity_kbd"],
                lat=ref["lat"], lon=ref["lon"],
            )
            for crude_name in ref["crude_types"]:
                session.run(
                    "MATCH (r:Refinery {name: $rname}), (g:CrudeGrade {name: $gname}) "
                    "MERGE (r)-[:COMPATIBLE_WITH]->(g)",
                    rname=ref["name"], gname=crude_name,
                )

        # Chokepoint route connections (for fallback traversal)
        _CHOKEPOINT_ROUTES = [
            ("Strait of Hormuz",  "Suez Canal"),
            ("Strait of Hormuz",  "Cape of Good Hope"),
            ("Suez Canal",        "Bab-el-Mandeb"),
            ("Bab-el-Mandeb",     "Cape of Good Hope"),
            ("Strait of Malacca", "Cape of Good Hope"),
            ("Turkish Straits",   "Suez Canal"),
        ]
        for src, dst in _CHOKEPOINT_ROUTES:
            session.run(
                "MATCH (a:Chokepoint {name: $src}), (b:Chokepoint {name: $dst}) "
                "MERGE (a)-[:CONNECTS_TO]->(b)",
                src=src, dst=dst,
            )

        counts = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS c"
        ).data()
        logger.info("Graph seeded: %s", {r["label"]: r["c"] for r in counts})


# ---------------------------------------------------------------------------
# Query Functions
# ---------------------------------------------------------------------------

def update_port_congestion(port_name: str, score: float) -> None:
    """Update the current_congestion_score for an ExportPort."""
    driver = get_driver()
    if driver is None:
        return
    try:
        with driver.session() as session:
            session.run(
                """
                MATCH (p:ExportPort {name: $port_name})
                SET p.current_congestion_score = $score
                """,
                port_name=port_name,
                score=score
            )
    except Exception as exc:
        logger.error("update_port_congestion failed: %s", exc)


def get_refinery_coords(refinery_name: str) -> dict[str, float] | None:
    """
    Return lat/lon for a named refinery node.

    Args:
        refinery_name: Exact Refinery node name.

    Returns:
        Dict with 'lat', 'lon', 'name', 'country' or None if not found.
    """
    driver = get_driver()

    # Fallback: scan seed data directly
    def _fallback():
        for r in _REFINERIES:
            if r["name"] == refinery_name:
                return {"name": r["name"], "country": r["country"], "lat": r["lat"], "lon": r["lon"]}
        return None

    if driver is None:
        return _fallback()

    try:
        with driver.session() as session:
            row = session.run(
                "MATCH (r:Refinery {name: $name}) RETURN r.lat AS lat, r.lon AS lon, r.country AS country",
                name=refinery_name,
            ).single()
            if row:
                return {"name": refinery_name, "country": row["country"], "lat": row["lat"], "lon": row["lon"]}
            return _fallback()
    except Exception as exc:
        logger.error("get_refinery_coords failed: %s", exc)
        return _fallback()

def get_crude_specs(grade_name: str) -> dict[str, float] | None:
    """Return api_gravity and sulphur_pct for a crude grade."""
    driver = get_driver()
    
    def _fallback():
        for g in _CRUDE_GRADES:
            if g["name"] == grade_name:
                return {"api_gravity": g["api_gravity"], "sulphur_pct": g["sulphur_pct"]}
        return None

    if driver is None:
        return _fallback()

    try:
        with driver.session() as session:
            row = session.run(
                "MATCH (g:CrudeGrade {name: $name}) RETURN g.api_gravity AS api, g.sulphur_pct AS sulphur",
                name=grade_name,
            ).single()
            if row:
                return {"api_gravity": row["api"], "sulphur_pct": row["sulphur"]}
            return _fallback()
    except Exception as exc:
        logger.error("get_crude_specs failed: %s", exc)
        return _fallback()

def get_grade_suppliers(grade_name: str) -> list[str]:
    """Return a unique list of countries that export the specified crude grade."""
    driver = get_driver()

    def _fallback():
        countries = set()
        for p in _EXPORT_PORTS:
            if grade_name in p["available_grades"]:
                countries.add(p["country"])
        return list(countries)

    if driver is None:
        return _fallback()

    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (p:ExportPort)-[:EXPORTS]->(g:CrudeGrade {name: $name}) "
                "RETURN DISTINCT p.country AS country",
                name=grade_name,
            )
            records = result.data()
            if records:
                return [r["country"] for r in records]
            return _fallback()
    except Exception as exc:
        logger.error("get_grade_suppliers failed: %s", exc)
        return _fallback()

def get_all_refineries() -> list[dict[str, Any]]:
    """
    Return all refinery nodes with name, country, capacity and coordinates.
    Used to populate the destination refinery dropdown in the UI.
    """
    driver = get_driver()
    if driver is None:
        return [
            {"name": r["name"], "country": r["country"],
             "capacity_kbd": r["capacity_kbd"], "lat": r["lat"], "lon": r["lon"]}
            for r in _REFINERIES
        ]

    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Refinery) "
                "RETURN r.name AS name, r.country AS country, "
                "       r.capacity_kbd AS capacity_kbd, r.lat AS lat, r.lon AS lon "
                "ORDER BY r.capacity_kbd DESC"
            )
            data = result.data()
            return data if data else [
                {"name": r["name"], "country": r["country"],
                 "capacity_kbd": r["capacity_kbd"], "lat": r["lat"], "lon": r["lon"]}
                for r in _REFINERIES
            ]
    except Exception as exc:
        logger.error("get_all_refineries failed: %s", exc)
        return [
            {"name": r["name"], "country": r["country"],
             "capacity_kbd": r["capacity_kbd"], "lat": r["lat"], "lon": r["lon"]}
            for r in _REFINERIES
        ]


def find_export_ports_bypassing(
    blocked_chokepoint: str,
    grade: str | None = None,
) -> list[dict[str, Any]]:
    """
    Find export terminals that:
      1. Export the requested crude grade (if provided)
      2. Do NOT require transiting the blocked chokepoint

    Args:
        blocked_chokepoint: Chokepoint name to avoid (e.g. "Strait of Hormuz").
        grade:              Optional crude grade filter (e.g. "Arab Light").

    Returns:
        List of dicts: name, country, grade, baseline_days_to_india, lat, lon.
    """
    driver = get_driver()
    if driver is None:
        logger.warning("Neo4j unavailable — returning fallback export ports.")
        ports = _FALLBACK_EXPORT_PORTS.get(blocked_chokepoint, [])
        if grade:
            ports = [p for p in ports if p.get("grade") == grade]
        return ports

    try:
        with driver.session() as session:
            if grade:
                result = session.run(
                    """
                    MATCH (p:ExportPort)-[:EXPORTS]->(g:CrudeGrade {name: $grade})
                    WHERE NOT (p)-[:SHIPS_THROUGH]->(:Chokepoint {name: $blocked})
                    RETURN p.name                  AS name,
                           p.country               AS country,
                           g.name                  AS grade,
                           g.api_gravity           AS api_gravity,
                           g.sulphur_pct           AS sulphur_pct,
                           p.baseline_days_to_india AS baseline_days_to_india,
                           p.lat                   AS lat,
                           p.lon                   AS lon,
                           p.current_congestion_score AS congestion_score,
                           [(p)-[:SHIPS_THROUGH]->(c) | c.name] AS transit_chokepoints
                    ORDER BY p.baseline_days_to_india ASC
                    """,
                    blocked=blocked_chokepoint,
                    grade=grade,
                )
            else:
                result = session.run(
                    """
                    MATCH (p:ExportPort)-[:EXPORTS]->(g:CrudeGrade)
                    WHERE NOT (p)-[:SHIPS_THROUGH]->(:Chokepoint {name: $blocked})
                    RETURN p.name                  AS name,
                           p.country               AS country,
                           g.name                  AS grade,
                           g.api_gravity           AS api_gravity,
                           g.sulphur_pct           AS sulphur_pct,
                           p.baseline_days_to_india AS baseline_days_to_india,
                           p.lat                   AS lat,
                           p.lon                   AS lon,
                           p.current_congestion_score AS congestion_score,
                           [(p)-[:SHIPS_THROUGH]->(c) | c.name] AS transit_chokepoints
                    ORDER BY p.baseline_days_to_india ASC
                    LIMIT 50
                    """,
                    blocked=blocked_chokepoint,
                )
            records = result.data()

        if not records:
            # Grade not available from any unblocked port
            logger.info("No export ports found for grade=%s bypassing %s.", grade, blocked_chokepoint)
            return []

        return records

    except Exception as exc:
        logger.error("find_export_ports_bypassing failed: %s", exc)
        return _FALLBACK_EXPORT_PORTS.get(blocked_chokepoint, [])


def match_refineries_to_crude(crude_grade: str) -> list[dict[str, Any]]:
    """
    Find refineries compatible with a given crude grade via the graph.

    Args:
        crude_grade: CrudeGrade node name (e.g. "Arab Light").

    Returns:
        List of refinery dicts with name, country, capacity_kbd.
    """
    driver = get_driver()
    if driver is None:
        return _FALLBACK_REFINERY_MATCHES.get(crude_grade, [])

    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (r:Refinery)-[:COMPATIBLE_WITH]->(g:CrudeGrade {name: $grade})
                RETURN r.name         AS refinery,
                       r.country      AS country,
                       r.capacity_kbd AS capacity_kbd
                ORDER BY r.capacity_kbd DESC
                """,
                grade=crude_grade,
            )
            data = result.data()
            return data if data else _FALLBACK_REFINERY_MATCHES.get(crude_grade, [])
    except Exception as exc:
        logger.error("match_refineries_to_crude failed: %s", exc)
        return _FALLBACK_REFINERY_MATCHES.get(crude_grade, [])


def find_alternative_routes(blocked_chokepoint: str) -> list[dict[str, Any]]:
    """
    Legacy: Find alternative chokepoint routes (used by modeler_agent resilience scoring).
    """
    driver = get_driver()
    if driver is None:
        return _FALLBACK_ROUTES.get(blocked_chokepoint, [])

    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (blocked:Chokepoint {name: $blocked})
                MATCH (alt:Chokepoint)
                WHERE alt.name <> $blocked
                  AND NOT (alt)-[:CONNECTS_TO]->(:Chokepoint {name: $blocked})
                RETURN alt.name        AS route,
                       alt.flow_mb_day AS flow_mb_day,
                       alt.region      AS region
                ORDER BY alt.flow_mb_day DESC
                LIMIT 5
                """,
                blocked=blocked_chokepoint,
            )
            records = result.data()

        if not records:
            return _FALLBACK_ROUTES.get(blocked_chokepoint, [])

        _DETOUR_LOOKUP = {
            "Cape of Good Hope":   {"detour_days": 14, "cost_premium_pct": 20},
            "Suez Canal":          {"detour_days": 2,  "cost_premium_pct": 5},
            "Bab-el-Mandeb":       {"detour_days": 4,  "cost_premium_pct": 10},
            "Strait of Malacca":   {"detour_days": 1,  "cost_premium_pct": 3},
            "Turkish Straits":     {"detour_days": 3,  "cost_premium_pct": 8},
            "Strait of Gibraltar": {"detour_days": 5,  "cost_premium_pct": 12},
            "Panama Canal":        {"detour_days": 7,  "cost_premium_pct": 15},
        }
        alternatives = []
        for rec in records:
            detour = _DETOUR_LOOKUP.get(rec["route"], {"detour_days": 10, "cost_premium_pct": 15})
            alternatives.append({
                "route":             rec["route"],
                "detour_days":       detour["detour_days"],
                "cost_premium_pct":  detour["cost_premium_pct"],
                "risk_score":        round(0.5 / max(rec.get("flow_mb_day", 1), 1), 3),
            })
        return alternatives

    except Exception as exc:
        logger.error("find_alternative_routes failed: %s", exc)
        return _FALLBACK_ROUTES.get(blocked_chokepoint, [])


def get_all_chokepoints() -> list[dict[str, Any]]:
    """Return all chokepoint nodes — used to populate dashboard dropdowns."""
    driver = get_driver()
    if driver is None:
        return [{"name": cp["name"], "flow_mb_day": cp["flow_mb_day"]} for cp in _CHOKEPOINTS]

    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (c:Chokepoint) RETURN c.name AS name, c.flow_mb_day AS flow_mb_day "
                "ORDER BY c.flow_mb_day DESC"
            )
            return result.data()
    except Exception as exc:
        logger.error("get_all_chokepoints failed: %s", exc)
        return [{"name": cp["name"], "flow_mb_day": cp["flow_mb_day"]} for cp in _CHOKEPOINTS]


def get_graph_stats() -> dict[str, int]:
    """Return node counts per label — for dashboard metadata display."""
    driver = get_driver()
    if driver is None:
        return {
            "Chokepoint": len(_CHOKEPOINTS),
            "ExportPort": len(_EXPORT_PORTS),
            "Refinery":   len(_REFINERIES),
            "CrudeGrade": len(_CRUDE_GRADES),
        }

    try:
        with driver.session() as session:
            stats = {}
            for label in ["Chokepoint", "ExportPort", "Refinery", "CrudeGrade"]:
                count = session.run(
                    f"MATCH (n:{label}) RETURN count(n) AS c"
                ).single()["c"]
                stats[label] = count
            return stats
    except Exception as exc:
        logger.error("get_graph_stats failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# CLI Entry Point: seed the graph
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    seed_graph()
    stats = get_graph_stats()
    print("Graph node counts:", stats)
    close_driver()
