"""
src/agents/sentinel_agent.py
─────────────────────────────
Geopolitical risk parsing and scoring engine powered by Gemini 2.0 Flash.

Reads unprocessed news headlines from the local Postgres news_cache,
packs them into structured batches, submits to Gemini for risk scoring,
then writes the scored risk events back to Postgres.

Rate Limit Guardrail:
  - Gemini 2.0 Flash free tier: 15 RPM
  - Batch size: 5 headlines per request → max 3 requests/cycle by default
  - tenacity exponential backoff on 429 errors
  - Logs [RATE GUARD] when approaching 12 RPM in a rolling window
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from google import genai
from google.genai import types
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from dotenv import load_dotenv

load_dotenv(override=True)
from src.database.postgres_db import (
    fetch_unprocessed_news,
    mark_news_processed,
    upsert_risk_event,
    fetch_latest_prices,
)
from src.ingestion.market_trawler import get_brent_rolling_stats
from src.ingestion.freight_trawler import get_freight_rolling_stats
from src.utils.metrics import (
    supply_disruption_index,
    normalise_price_delta,
    normalise_vessel_density_delta,
    normalise_freight_delta,
)

load_dotenv()
logger = logging.getLogger(__name__)

from src.utils.constants import (
    CHOKEPOINTS_SET,
    SENTINEL_GEMINI_MODEL,
    SENTINEL_DELTA_D_HIGH,
    SENTINEL_DELTA_D_LOW,
    SENTINEL_SEVERITY_THRESHOLD,
)

# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        # The genai SDK prefers GOOGLE_API_KEY if both are set, which can cause
        # Auth errors if a global/stale GOOGLE_API_KEY exists in the user's terminal.
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
        _client = genai.Client(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Rate Limit Guard
# ---------------------------------------------------------------------------

_request_timestamps: deque = deque(maxlen=60)
_RPM_LIMIT = 15
_RPM_WARN  = 12


def _check_rate_limit() -> None:
    """Block execution if approaching RPM limit; log a warning at the threshold."""
    now = time.monotonic()
    # Remove timestamps older than 60 seconds
    while _request_timestamps and now - _request_timestamps[0] > 60:
        _request_timestamps.popleft()

    recent_count = len(_request_timestamps)

    if recent_count >= _RPM_LIMIT:
        sleep_time = 62 - (now - _request_timestamps[0])
        logger.warning("[RATE GUARD] RPM limit reached. Sleeping %.1fs.", sleep_time)
        time.sleep(max(sleep_time, 1))
    elif recent_count >= _RPM_WARN:
        logger.warning("[RATE GUARD] Approaching RPM limit (%d/%d). Slowing down.", recent_count, _RPM_LIMIT)
        time.sleep(4)

    _request_timestamps.append(time.monotonic())


# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an energy supply chain geopolitical risk analyst.
Analyse the following news headlines and return a JSON object with this exact schema:

{
  "region": "<geographic region, e.g. Persian Gulf>",
  "disruption_type": "<one of: military_conflict | sanctions | weather | accident | piracy | protest | unknown>",
  "severity": <float 0.0 to 1.0>,
  "affected_chokepoints": ["<chokepoint name>", ...],
  "confidence": <float 0.0 to 1.0>,
  "summary": "<1-2 sentence plain-English risk summary>"
}

Return ONLY valid JSON. No markdown fences. No explanations outside the JSON.
If no relevant disruption is detected, return severity: 0.1 and disruption_type: unknown.
"""

_VALID_CHOKEPOINTS = {
    "Strait of Hormuz", "Suez Canal", "Bab-el-Mandeb",
    "Strait of Malacca", "Turkish Straits", "Cape of Good Hope",
    "Strait of Gibraltar", "Panama Canal",
}


def _build_prompt(headlines: list[str]) -> str:
    """Format a list of headlines into the Sentinel analysis prompt."""
    numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
    return f"{_SYSTEM_PROMPT}\n\nHeadlines:\n{numbered}"


# ---------------------------------------------------------------------------
# Gemini Call with Retry
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    stop=stop_after_attempt(3),
    reraise=False,
)
def _call_gemini(prompt: str) -> dict[str, Any] | None:
    """Submit a prompt to Gemini 2.0 Flash and parse the JSON response."""
    _check_rate_limit()
    client = _get_client()

    response = client.models.generate_content(
        model=SENTINEL_GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,       # Low temperature for structured factual output
        ),
    )

    text = response.text.strip()

    # Strip markdown fences if Gemini wraps output
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    parsed = json.loads(text)

    # Validate and sanitise chokepoints against known list
    if "affected_chokepoints" in parsed:
        parsed["affected_chokepoints"] = [
            cp for cp in parsed["affected_chokepoints"]
            if cp in CHOKEPOINTS_SET
        ]

    return parsed


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def process_unprocessed_batch(batch_size: int = 5) -> int:
    """
    Fetch unprocessed news, score via Gemini, compute SDI, write risk events.

    Args:
        batch_size: Max headlines to pack into a single Gemini request.

    Returns:
        Number of risk events written to Postgres.
    """
    if not os.getenv("GEMINI_API_KEY", ""):
        logger.warning("sentinel_agent: GEMINI_API_KEY not configured — skipping. "
                       "Risk scoring disabled until key is set.")
        return 0

    rows = fetch_unprocessed_news(limit=batch_size)
    if not rows:
        logger.info("sentinel_agent: no unprocessed news to score.")
        return 0

    headlines = [r["title"] for r in rows if r.get("title")]
    news_ids  = [r["id"] for r in rows]

    if not headlines:
        mark_news_processed(news_ids)
        return 0

    prompt = _build_prompt(headlines)

    try:
        scored = _call_gemini(prompt)
    except Exception as exc:
        logger.error("sentinel_agent: Gemini call failed — %s", exc)
        return 0

    if scored is None:
        return 0

    # Allow non-events through so the risk baseline decays properly.
    if scored.get("disruption_type", "").lower() == "unknown" or scored.get("severity", 1.0) <= 0.1:
        logger.info("sentinel_agent: No disruption signal detected. Inserting baseline event to allow SDI decay.")

    # Enrich SDI score using market data
    brent_stats = get_brent_rolling_stats()
    delta_p = normalise_price_delta(
        current_price=brent_stats["current_price"],
        rolling_mean=brent_stats["rolling_mean"],
        rolling_std=brent_stats["rolling_std"],
    )

    freight_stats = get_freight_rolling_stats()
    delta_p_freight = normalise_freight_delta(
        current_freight=freight_stats["current_price"],
        rolling_mean=freight_stats["rolling_mean"],
        rolling_std=freight_stats["rolling_std"],
    )

    # vessel density divergence — approximated when live AIS baseline is unavailable
    delta_d = (
        SENTINEL_DELTA_D_HIGH
        if scored.get("severity", 0) > SENTINEL_SEVERITY_THRESHOLD
        else SENTINEL_DELTA_D_LOW
    )

    sdi = supply_disruption_index(
        p_risk=float(scored.get("severity", 0.0)),
        delta_d_vessel=delta_d,
        delta_p_price=delta_p,
        delta_p_freight=delta_p_freight,
    )

    event = {**scored, "sdi_score": sdi}
    upsert_risk_event(event)
    mark_news_processed(news_ids)

    logger.info(
        "sentinel_agent: scored batch — region=%s severity=%.2f SDI=%.1f",
        scored.get("region"), scored.get("severity", 0), sdi,
    )
    return 1


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if "--test" in sys.argv:
        # Inject a synthetic test headline for validation without DB dependency
        prompt = _build_prompt([
            "Iranian Revolutionary Guard seizes oil tanker in Strait of Hormuz",
            "Houthi drones target Saudi Aramco pipeline infrastructure",
        ])
        result = _call_gemini(prompt)
        print("Test result:", json.dumps(result, indent=2))
    else:
        count = process_unprocessed_batch()
        print(f"Events written: {count}")
