"""
src/agents/sentinel_agent.py
─────────────────────────────
Geopolitical risk parsing and scoring engine powered by Gemini 2.5 Flash.

Reads unprocessed news headlines from the local Postgres news_cache,
packs them into structured batches, submits to Gemini for risk scoring,
then writes the scored risk events back to Postgres.

Rate Limit Guardrail:
  - Gemini 2.5 Flash free tier: 15 RPM
  - Batch size: 10 headlines per request
  - tenacity exponential backoff on 429 errors
  - Logs [RATE GUARD] when approaching 12 RPM in a rolling window
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from typing import Any
from urllib.parse import urlparse

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
)
from src.ingestion.market_trawler import get_brent_rolling_stats
from src.ingestion.freight_trawler import get_freight_rolling_stats
from src.utils.metrics import (
    supply_disruption_index,
    normalise_price_delta,
    normalise_freight_delta,
)

logger = logging.getLogger(__name__)

from src.utils.constants import (
    CHOKEPOINTS_SET,
    SENTINEL_GEMINI_MODEL,
    SENTINEL_DELTA_D_HIGH,
    SENTINEL_DELTA_D_LOW,
    SENTINEL_SEVERITY_THRESHOLD,
)

# ---------------------------------------------------------------------------
# News source credibility mix
# ---------------------------------------------------------------------------

# Sentinel can receive records from backfills or future ingestion sources, so
# scoring-time balancing must not depend on GDELT's upstream filtering alone.
MAJOR_GLOBAL: frozenset[str] = frozenset({
    'reuters.com', 'bloomberg.com', 'ft.com', 'wsj.com', 'cnbc.com',
    'bbc.com', 'cnn.com', 'apnews.com', 'nytimes.com', 'economist.com',
    'theguardian.com', 'washingtonpost.com', 'dw.com', 'france24.com',
    'nbcnews.com', 'abcnews.go.com', 'cbsnews.com',
})

INDUSTRIAL: frozenset[str] = frozenset({
    'spglobal.com', 'oilprice.com', 'lloydslist.com', 'tradewindsnews.com',
    'maritime-executive.com', 'argusmedia.com', 'platts.com', 'eia.gov',
    'iea.org', 'rigzone.com', 'upstreamonline.com', 'worldoil.com',
    'energyintel.com', 'offshore-energy.biz', 'hellenicshippingnews.com',
    'shippingwatch.com',
})

LOCAL: frozenset[str] = frozenset({
    'aljazeera.com', 'middleeasteye.net', 'thenationalnews.com',
    'arabnews.com', 'gulfnews.com', 'khaleejtimes.com', 'alarabiya.net',
    'jpost.com', 'haaretz.com', 'dawn.com', 'thehindu.com',
    'timesofindia.indiatimes.com', 'hindustantimes.com',
})

_SOURCE_QUOTAS: tuple[tuple[str, float], ...] = (
    ('major_global', 0.60),
    ('industrial', 0.20),
    ('local', 0.20),
)


def _hostname(url: str) -> str:
    value = (url or '').strip()
    if not value:
        return ''
    parsed = urlparse(value if '://' in value else f'//{value}')
    return (parsed.hostname or '').lower().rstrip('.')


def _matches_domain(hostname: str, domains: frozenset[str]) -> bool:
    return any(hostname == domain or hostname.endswith(f'.{domain}') for domain in domains)


def _source_category(url: str) -> str:
    hostname = _hostname(url)
    if _matches_domain(hostname, MAJOR_GLOBAL):
        return 'major_global'
    if _matches_domain(hostname, INDUSTRIAL):
        return 'industrial'
    if _matches_domain(hostname, LOCAL):
        return 'local'
    return 'unclassified'


def _source_quotas(batch_size: int) -> dict[str, int]:
    major = int(batch_size * _SOURCE_QUOTAS[0][1])
    industrial = int(batch_size * _SOURCE_QUOTAS[1][1])
    return {
        'major_global': major,
        'industrial': industrial,
        'local': batch_size - major - industrial,
    }


def _select_balanced_batch(rows: list[dict[str, Any]], batch_size: int) -> list[dict[str, Any]]:
    # Rows within buckets and fallback candidates retain DB recency order.
    if batch_size <= 0 or not rows:
        return []

    target_size = min(batch_size, len(rows))
    indexed_rows = list(enumerate(rows))
    buckets: dict[str, list[int]] = {
        'major_global': [],
        'industrial': [],
        'local': [],
        'unclassified': [],
    }
    for index, row in indexed_rows:
        buckets[_source_category(str(row.get('url', '')))].append(index)

    selected: list[int] = []
    selected_set: set[int] = set()
    quotas = _source_quotas(target_size)
    for category, _ in _SOURCE_QUOTAS:
        for index in buckets[category][:quotas[category]]:
            selected.append(index)
            selected_set.add(index)

    # Fill category shortfalls from all leftovers, including unclassified URLs.
    for index, _ in indexed_rows:
        if len(selected) >= target_size:
            break
        if index not in selected_set:
            selected.append(index)
            selected_set.add(index)

    # Preserve the earlier content-coverage guarantee independently of source
    # balancing. Prefer a same-source swap so the 60/20/20 mix remains intact.
    required_article_categories = tuple(
        category
        for category in ('producer_nation', 'chokepoint')
        if any(row.get('article_category') == category for row in rows)
    )
    if target_size >= len(required_article_categories):
        for required_category in required_article_categories:
            if any(
                rows[index].get('article_category') == required_category
                for index in selected
            ):
                continue

            candidates = [
                index
                for index, row in indexed_rows
                if index not in selected_set
                and row.get('article_category') == required_category
            ]
            replacement: tuple[int, int] | None = None
            for candidate in candidates:
                candidate_source = _source_category(str(rows[candidate].get('url', '')))
                for position in range(len(selected) - 1, -1, -1):
                    current = selected[position]
                    current_category = rows[current].get('article_category')
                    current_category_count = sum(
                        rows[index].get('article_category') == current_category
                        for index in selected
                    )
                    protects_required_category = (
                        current_category in required_article_categories
                        and current_category_count == 1
                    )
                    same_source = (
                        _source_category(str(rows[current].get('url', '')))
                        == candidate_source
                    )
                    if same_source and not protects_required_category:
                        replacement = (position, candidate)
                        break
                if replacement:
                    break

            # If no same-source swap exists, category coverage wins over the
            # target mix; the domain ratios are aims with documented fallback.
            if replacement is None and candidates:
                for position in range(len(selected) - 1, -1, -1):
                    current = selected[position]
                    current_category = rows[current].get('article_category')
                    current_category_count = sum(
                        rows[index].get('article_category') == current_category
                        for index in selected
                    )
                    if not (
                        current_category in required_article_categories
                        and current_category_count == 1
                    ):
                        replacement = (position, candidates[0])
                        break

            if replacement:
                position, candidate = replacement
                selected_set.remove(selected[position])
                selected[position] = candidate
                selected_set.add(candidate)

    return [rows[index] for index in selected]

# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------

_clients: list[genai.Client] | None = None
_key_index: int = 0


def _api_keys() -> list[str]:
    """All configured Gemini keys, in preference order.

    GEMINI_API_KEY holds the primary; GEMINI_API_KEYS may hold a comma-separated
    pool. The free tier is capped per key, so spreading batches across several
    keys is what keeps the Sentinel scoring during a news burst.
    """
    keys: list[str] = []
    primary = os.getenv("GEMINI_API_KEY", "").strip()
    if primary:
        keys.append(primary)
    for extra in os.getenv("GEMINI_API_KEYS", "").split(","):
        candidate = extra.strip()
        if candidate and candidate not in keys:
            keys.append(candidate)
    return keys


def _get_clients() -> list[genai.Client]:
    global _clients
    if _clients is None:
        keys = _api_keys()
        if not keys:
            raise ValueError("GEMINI_API_KEY not set in .env")
        # The genai SDK prefers GOOGLE_API_KEY if both are set, which can cause
        # Auth errors if a global/stale GOOGLE_API_KEY exists in the user's terminal.
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
        _clients = [genai.Client(api_key=key) for key in keys]
        logger.info("sentinel_agent: %d Gemini key(s) configured.", len(_clients))
    return _clients


def _get_client() -> genai.Client:
    """Current client in the rotation."""
    clients = _get_clients()
    return clients[_key_index % len(clients)]


def _rotate_key() -> bool:
    """Advance to the next key. Returns False when the pool is exhausted."""
    global _key_index
    clients = _get_clients()
    if len(clients) < 2:
        return False
    _key_index = (_key_index + 1) % len(clients)
    logger.warning(
        "sentinel_agent: quota hit — rotating to Gemini key %d/%d.",
        _key_index + 1,
        len(clients),
    )
    return True


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
Analyse the following numbered news headlines. They frequently describe SEVERAL
UNRELATED incidents, so return one object per distinct incident:

{
  "events": [
    {
      "headline_indices": [<numbers of the headlines this incident is drawn from>],
      "region": "<geographic region, e.g. Persian Gulf>",
      "disruption_type": "<one of: military_conflict | sanctions | producer_supply_shock | embargo | weather | accident | piracy | protest | unknown>",
      "severity": <float 0.0 to 1.0>,
      "severity_reasoning": "<A detailed, structured, multi-paragraph explanation of the exact numeric score>",
      "affected_chokepoints": ["<chokepoint name>", ...],
      "directly_affected_chokepoints": ["<chokepoint with actual shipping/mining/closure threats>", ...],
      "affected_producer_countries": ["<country name>", ...],
      "directly_affected_producer_countries": ["<country with proven production/export impairment>", ...],
      "confidence": <float 0.0 to 1.0>,
      "summary": "<A comprehensive, multi-paragraph plain-English intelligence briefing>"
    }
  ]
}

Return ONLY valid JSON. No markdown fences. No explanations outside the JSON.

Grouping rules — these matter as much as the scoring:
- Group headlines together ONLY when they report the SAME underlying incident.
  Multiple outlets covering one event is one object.
- Split incidents that differ in disruption_type. A sanctions package and a
  missile strike are two objects even when both involve the same country;
  merging them loses the sanctions signal entirely and misdates its decay.
- Do not force every headline into the dominant story of the batch. A single
  headline about a refinery fire, a storm closure, a pipeline strike, or a
  hijacking is its own object even when the rest of the batch is about a war.
- headline_indices must reference the numbers shown beside each headline, and
  every index must appear in exactly one object.
- Omit headlines with no energy-supply relevance rather than inventing an
  incident for them. If NONE are relevant, return a single object covering all
  of them with severity 0.1 and disruption_type unknown.
- disruption_type must be the most specific accurate value. Reserve
  military_conflict for armed action; use sanctions/embargo for policy
  measures, weather for storm or ice closures, accident for fires, explosions,
  spills and groundings, piracy for hijacking or armed boarding, and protest
  for strikes, blockades and labour action.
Depth and calibration requirements:
- severity_reasoning must contain four clearly labelled sections separated by
  blank lines: "Incident facts", "Supply-chain impact", "Geopolitical context",
  and "Score calibration". Use concise bullet points beneath a section when
  several drivers are present. Encode paragraph and bullet line breaks as \\n
  inside the JSON string so the response remains valid JSON.
- Incident facts must identify what the headlines actually establish, note
  corroboration or contradictions across headlines, and distinguish reported
  facts from inference. Never invent facts that are absent from the headlines.
- Supply-chain impact must trace the plausible mechanism from the incident to
  production, export terminals, chokepoints, tanker flows, freight/insurance,
  crude availability, or prices. State when no direct physical disruption is
  yet established.
- affected_chokepoints may contain any chokepoint mentioned as exposed to the
  conflict or transit disruption.
- directly_affected_chokepoints is the strict subset for which actual shipping
  attacks, mining, blockades, or closures are established within the chokepoint
  itself. A conflict in the broader region without a specific threat to the
  strait is not a direct chokepoint impairment.
- affected_producer_countries may contain only producing countries with a
  material direct or transit exposure. Do not include belligerents, base-host
  countries, consumers, or diplomatic actors merely because they are named.
- directly_affected_producer_countries is the strict subset for which a
  production field, pipeline, refinery, export terminal, loading operation, or
  national export capability is reported impaired. A nearby attack or a
  chokepoint threat alone is not direct producer impairment. Use an empty list
  when the headlines do not establish this.
- Geopolitical context must explain escalation potential, actor intent or
  policy constraints, geographic exposure, duration, and relevant uncertainty.
- Score calibration must explicitly justify the precise severity value (for
  example, why 0.90 rather than 0.70 or 1.00), identify upward and downward
  score drivers, and relate the score to the 0.0-1.0 scale. The numeric value
  discussed here must exactly match the severity field.
- summary must be 5-7 substantive sentences across two short paragraphs. It
  should synthesize the incident, the energy-supply transmission path, the
  exposed regions/assets, and the most important forward-looking indicator.


For producer_supply_shock events: if no chokepoint is directly mentioned in the
headlines, you MAY infer downstream transit risk. E.g. Russian export freeze ->
Turkish Straits; Nigerian NNPC shutdown -> Cape of Good Hope. When inferring,
set confidence <= 0.70 to signal uncertainty. Always populate
affected_producer_countries accurately even if chokepoints are empty.
"""


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
    """Submit a prompt to Gemini and parse the JSON response.

    On a quota rejection the call is retried against the next configured key
    before the tenacity backoff kicks in — a second key answers immediately,
    whereas waiting out a per-key daily cap would stall scoring for hours.
    """
    _check_rate_limit()

    attempts = len(_get_clients())
    last_error: Exception | None = None
    for _ in range(attempts):
        client = _get_client()
        try:
            response = client.models.generate_content(
                model=SENTINEL_GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,   # Low temperature for structured factual output
                ),
            )
            break
        except Exception as exc:      # noqa: BLE001 — SDK raises bare ClientError
            last_error = exc
            message = str(exc)
            quota_hit = "429" in message or "RESOURCE_EXHAUSTED" in message
            if not (quota_hit and _rotate_key()):
                raise
    else:
        if last_error:
            raise last_error
        return None

    text = response.text.strip()
    return _parse_gemini_events(text)


def _strip_fences(text: str) -> str:
    """Remove markdown fences if the model wrapped its output."""
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text


def _parse_gemini_events(text: str) -> list[dict[str, Any]]:
    """Parse a scoring response into one normalised record per incident.

    The model is asked for `{"events": [...]}` so that a batch containing, say,
    a sanctions package and a missile strike yields two records rather than
    collapsing into whichever theme dominated. Single-object and bare-array
    responses are still accepted, since one malformed reply should degrade to
    one event rather than losing the whole batch.
    """
    data = json.loads(_strip_fences(text))

    if isinstance(data, dict) and isinstance(data.get("events"), list):
        raw_events = data["events"]
    elif isinstance(data, list):
        raw_events = data
    else:
        raw_events = [data]

    events = []
    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        try:
            events.append(_normalise_event(raw))
        except Exception as exc:      # noqa: BLE001 — skip one bad record, keep the rest
            logger.warning("sentinel_agent: dropping unparseable event - %s", exc)
    return events


def _parse_gemini_response(text: str) -> dict[str, Any]:
    """Parse and canonicalize a single-event JSON response from Gemini."""
    return _normalise_event(json.loads(_strip_fences(text)))


def _normalise_event(parsed: dict[str, Any]) -> dict[str, Any]:
    """Canonicalise chokepoints and producer countries on one scored event."""
    # Validate and sanitise chokepoints against known list
    from src.utils.constants import canonical_chokepoint_name, CHOKEPOINTS_SET, PRODUCER_NATIONS, canonical_country_name

    for cp_field in ("affected_chokepoints", "directly_affected_chokepoints"):
        if cp_field in parsed:
            canonical_cps = []
            for cp in parsed[cp_field]:
                canonical = canonical_chokepoint_name(cp)
                if canonical in CHOKEPOINTS_SET:
                    if canonical != cp.strip():
                        logger.info("sentinel_agent: canonicalized chokepoint '%s' -> '%s'", cp, canonical)
                    canonical_cps.append(canonical)
            parsed[cp_field] = list(dict.fromkeys(canonical_cps))

    # Ensure directly affected is a subset
    parsed["affected_chokepoints"] = list(dict.fromkeys(
        (parsed.get("affected_chokepoints") or [])
        + (parsed.get("directly_affected_chokepoints") or [])
    ))

    valid_producers = {
        canonical_country_name(country) for country in PRODUCER_NATIONS
    }
    for field in (
        "affected_producer_countries",
        "directly_affected_producer_countries",
    ):
        values = parsed.get(field) or []
        parsed[field] = list(dict.fromkeys(
            canonical_country_name(country)
            for country in values
            if canonical_country_name(country) in valid_producers
        ))

    # Directly impaired producers are necessarily affected as well.
    parsed["affected_producer_countries"] = list(dict.fromkeys(
        parsed["affected_producer_countries"]
        + parsed["directly_affected_producer_countries"]
    ))

    return parsed


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def _rows_for_indices(
    batch: list[dict[str, Any]],
    indices: Any,
) -> list[dict[str, Any]]:
    """Map an event's 1-based `headline_indices` back onto the batch rows.

    Falls back to the whole batch when the model omits or mangles the indices,
    which keeps provenance attached (over-attributing sources is recoverable;
    silently storing an event with none is not).
    """
    if not isinstance(indices, list):
        return batch
    rows = []
    for raw in indices:
        try:
            position = int(raw) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= position < len(batch):
            rows.append(batch[position])
    return rows or batch


def _log_recent_type_distribution(limit: int = 40) -> None:
    """Log the disruption-type mix of recent events."""
    try:
        from collections import Counter

        from src.database.postgres_db import fetch_risk_events

        recent = fetch_risk_events(limit=limit)
        if not recent:
            return
        counts = Counter(
            str(e.get("disruption_type") or "unknown").lower() for e in recent
        )
        logger.info(
            "sentinel_agent: last %d events by type: %s",
            len(recent),
            dict(counts.most_common()),
        )
        dominant, dominant_n = counts.most_common(1)[0]
        if len(recent) >= 10 and dominant_n / len(recent) >= 0.9:
            logger.warning(
                "sentinel_agent: %.0f%% of recent events are '%s'. Either the "
                "ingestion queries lack vocabulary for the other types, or "
                "distinct incidents are being merged into one classification.",
                100 * dominant_n / len(recent),
                dominant,
            )
    except Exception as exc:      # noqa: BLE001 — diagnostics must never break scoring
        logger.debug("sentinel_agent: type distribution log failed - %s", exc)


def process_unprocessed_batch(batch_size: int = 10) -> int:
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

    candidate_pool_size = max(50, batch_size * 5)
    rows = fetch_unprocessed_news(limit=candidate_pool_size)
    if not rows:
        logger.info("sentinel_agent: no unprocessed news to score.")
        return 0

    batch = _select_balanced_batch(rows, batch_size)
    source_mix: dict[str, int] = {}
    for row in batch:
        category = _source_category(str(row.get("url", "")))
        source_mix[category] = source_mix.get(category, 0) + 1
    logger.info(
        "sentinel_agent: selected source mix %s from %d candidates.", source_mix, len(rows)
    )

    headlines = [r["title"] for r in batch if r.get("title")]
    source_urls = [r["url"] for r in batch if r.get("url")]
    news_ids  = [r["id"] for r in batch]

    if not headlines:
        mark_news_processed(news_ids)
        return 0

    prompt = _build_prompt(headlines)

    try:
        scored_events = _call_gemini(prompt)
    except Exception as exc:
        logger.error("sentinel_agent: Gemini call failed — %s", exc)
        return 0

    if not scored_events:
        return 0

    # Market context is shared by every event in the batch, so fetch it once.
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

    from collections import Counter

    written = 0
    type_counts: Counter[str] = Counter()

    for scored in scored_events:
        # Attribute only this incident's own headlines. Without this the whole
        # batch's URLs and timestamps would be stamped on every event, and the
        # newest headline would set the decay clock for an older incident.
        rows_for_event = _rows_for_indices(batch, scored.get("headline_indices"))

        severity = float(scored.get("severity", 0.0) or 0.0)
        disruption_type = str(scored.get("disruption_type", "unknown") or "unknown")

        delta_d = (
            SENTINEL_DELTA_D_HIGH
            if severity > SENTINEL_SEVERITY_THRESHOLD
            else SENTINEL_DELTA_D_LOW
        )
        sdi = supply_disruption_index(
            p_risk=severity,
            delta_d_vessel=delta_d,
            delta_p_price=delta_p,
            delta_p_freight=delta_p_freight,
        )

        category_counts = Counter(
            r.get("article_category", "general") for r in rows_for_event
        )
        dominant_category = (
            category_counts.most_common(1)[0][0] if category_counts else "general"
        )
        fetched_times = [
            r.get("fetched_at") for r in rows_for_event if r.get("fetched_at") is not None
        ]

        event = {
            **scored,
            "sdi_score": sdi,
            "source_urls": [r["url"] for r in rows_for_event if r.get("url")],
            "source_fetched_at": max(fetched_times, default=None),
            "article_category": dominant_category,
        }
        event.pop("headline_indices", None)
        upsert_risk_event(event)
        written += 1
        type_counts[disruption_type.lower()] += 1

        logger.info(
            "sentinel_agent: scored event — type=%s region=%s severity=%.2f "
            "SDI=%.1f from %d headline(s)",
            disruption_type,
            scored.get("region"),
            severity,
            sdi,
            len(rows_for_event),
        )

    mark_news_processed(news_ids)

    # Surface the type mix: a monoculture here means either the ingestion
    # queries lack vocabulary for the missing types, or distinct incidents are
    # still being merged. Neither is visible from the event count alone.
    logger.info(
        "sentinel_agent: batch produced %d event(s) from %d headline(s); types=%s",
        written,
        len(headlines),
        dict(type_counts),
    )
    _log_recent_type_distribution()
    return written


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
