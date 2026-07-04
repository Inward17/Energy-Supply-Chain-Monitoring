"""
src/ingestion/portwatch_trawler.py
──────────────────────────────────
Fetches port calls data from IMF PortWatch to calculate congestion.
"""

import logging
import urllib.request
import urllib.parse
import json

from src.database.neo4j_graph import update_port_congestion

logger = logging.getLogger(__name__)

# Map Neo4j ExportPort names to IMF PortWatch port names.
# Unmapped ports will be skipped with a warning and default to 0.5 in Fixer logic.
PORT_MAPPING = {
    "Ras Tanura": "Ras Tanura",
    "Mina Al Ahmadi": "Mina Al Ahmadi",
    "Kharg Island": "Kharg Island",
    "Basra Oil Terminal": "Basrah Oil Terminal",
    "Ruwais Export Terminal": "Al Ruwais",
    "Bonny Export Terminal": "Bonny",
    "Escravos Terminal": "Escravos (Oil Terminal)",
    "Galveston/Houston": "Houston",
    "Sullom Voe": "Sullom Voe",
    "Primorsk": "Primorsk",
    "Novorossiysk": "Novorossiysk",
    "Skikda": "Skikda (Port Methanier)",
}

def calculate_congestion_score(history: list[dict]) -> float:
    """
    Calculate congestion proxy using a 7-day vs 30-day trailing average.
    Assumption: A sustained drop in tanker port-calls relative to the 
    30-day baseline acts as a congestion proxy, on the assumption that 
    reduced completed calls reflects vessels backed up rather than reduced demand.
    
    Returns a score 0.0 to 1.0 (higher = worse congestion).
    """
    # House Style Note: Missing or insufficient data defaults to a neutral 
    # midpoint (0.5) to avoid artificially favoring unmonitored ports.
    if not history or len(history) < 14:
        return 0.5  # Neutral default

    if len(history) < 30:
        logger.warning("Short baseline for congestion: only %d days available (ideal is 30).", len(history))
        
    recent_7 = [h["portcalls_tanker"] for h in history[:7] if h.get("portcalls_tanker") is not None]
    baseline_30 = [h["portcalls_tanker"] for h in history[:30] if h.get("portcalls_tanker") is not None]
    
    if not recent_7 or not baseline_30:
        return 0.5
        
    avg_7 = sum(recent_7) / len(recent_7)
    avg_30 = sum(baseline_30) / len(baseline_30)
    
    # Low-Volume Noise Filter:
    # Based on a baseline pull of all 12 ports, 0.5 (1 ship every 2 days) cleanly 
    # separates genuinely active ports (Ras Tanura: 0.77, Primorsk: 1.43) from 
    # genuinely quiet ports (Sullom Voe: 0.07, Escravos: 0.13). For the latter,
    # a drop to zero is just statistical noise, not a reliable congestion signal.
    # House Style: Emit neutral 0.5 rather than penalising them.
    if avg_30 < 0.5:
        return 0.5
        
    ratio = avg_7 / avg_30
    
    # We define congestion_score: 1.0 - min(ratio, 1.0)
    # If ratio >= 1.0 (healthy or clearing), congestion = 0.0
    congestion = max(0.0, 1.0 - ratio)
    
    return round(congestion, 3)

def trawl_portwatch() -> None:
    """Fetch daily port traffic from IMF PortWatch API."""
    base_url = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query"
    
    logger.info("Starting IMF PortWatch trawler...")
    updated = 0
    
    for neo4j_name, imf_name in PORT_MAPPING.items():
        params = {
            "where": f"portname = '{imf_name}'",
            "outFields": "date,portcalls_tanker",
            "orderByFields": "date DESC",
            "outSR": "4326",
            "f": "json",
            "resultRecordCount": "30"
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
                features = data.get("features", [])
                history = [f.get("attributes", {}) for f in features]
                
                if not history:
                    logger.warning("No IMF PortWatch data found for '%s' (Neo4j: '%s')", imf_name, neo4j_name)
                    continue
                    
                score = calculate_congestion_score(history)
                update_port_congestion(neo4j_name, score)
                updated += 1
                
        except Exception as e:
            logger.error("Failed fetching PortWatch data for %s: %s", neo4j_name, e)
            
    logger.info("PortWatch trawler complete. Updated %d ports.", updated)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    trawl_portwatch()
