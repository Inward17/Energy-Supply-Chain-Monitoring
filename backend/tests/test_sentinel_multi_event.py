"""
tests/test_sentinel_multi_event.py
──────────────────────────────────
Regressions for multi-incident scoring.

The Sentinel used to send a batch of headlines to Gemini and store a single
event with one `disruption_type`. Measured on live data that averaged ~6.7
headlines collapsed into one classification, which made every minority topic
disappear: 56 of 60 stored events were `military_conflict` and 4 were
`unknown`, with zero sanctions, weather, accident, piracy or protest events
despite such headlines being present in news_cache.

That mattered beyond labelling — disruption_type selects the decay half-life,
so a sanctions story filed as military_conflict decayed 4.5x too fast
(10 days instead of 45).

No test performs a live Gemini call.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.agents import sentinel_agent as sentinel
from src.agents.sentinel_agent import (
    _parse_gemini_events,
    _parse_gemini_response,
    _rows_for_indices,
)

NOW = datetime.now(timezone.utc)


def _event(dtype, severity=0.5, indices=None, **extra):
    body = {
        "disruption_type": dtype,
        "severity": severity,
        "region": "Test Region",
        "confidence": 0.8,
        "summary": "s",
        "severity_reasoning": "r",
        "affected_chokepoints": [],
        "directly_affected_chokepoints": [],
        "affected_producer_countries": [],
        "directly_affected_producer_countries": [],
        **extra,
    }
    if indices is not None:
        body["headline_indices"] = indices
    return body


def _row(i, url, hours_old=1.0, category="general"):
    return {
        "id": i,
        "url": url,
        "title": f"headline {i}",
        "article_category": category,
        "fetched_at": NOW - timedelta(hours=hours_old),
    }


# ---------------------------------------------------------------------------
# Envelope parsing
# ---------------------------------------------------------------------------

def test_events_envelope_yields_one_record_per_incident():
    raw = json.dumps({"events": [_event("sanctions"), _event("weather"), _event("piracy")]})
    events = _parse_gemini_events(raw)
    assert [e["disruption_type"] for e in events] == ["sanctions", "weather", "piracy"]


def test_legacy_single_object_still_parses():
    """One malformed or old-style reply should degrade to one event, not lose
    the whole batch."""
    events = _parse_gemini_events(json.dumps(_event("military_conflict")))
    assert len(events) == 1
    assert events[0]["disruption_type"] == "military_conflict"


def test_bare_array_is_accepted():
    events = _parse_gemini_events(json.dumps([_event("embargo"), _event("accident")]))
    assert len(events) == 2


def test_markdown_fences_are_stripped():
    raw = "```json\n" + json.dumps({"events": [_event("protest")]}) + "\n```"
    assert _parse_gemini_events(raw)[0]["disruption_type"] == "protest"


def test_one_bad_record_does_not_discard_the_others():
    raw = json.dumps({"events": [_event("sanctions"), "not-an-object", _event("weather")]})
    events = _parse_gemini_events(raw)
    assert [e["disruption_type"] for e in events] == ["sanctions", "weather"]


def test_single_event_parser_still_canonicalises():
    """The per-event normaliser is shared, so canonicalisation must survive."""
    parsed = _parse_gemini_response(
        json.dumps(_event("military_conflict", affected_chokepoints=["Hormuz Strait"]))
    )
    assert parsed["affected_chokepoints"] == ["Strait of Hormuz"]


# ---------------------------------------------------------------------------
# Headline attribution
# ---------------------------------------------------------------------------

def test_indices_map_to_their_own_headlines():
    batch = [_row(1, "u1"), _row(2, "u2"), _row(3, "u3")]
    assert [r["url"] for r in _rows_for_indices(batch, [1, 3])] == ["u1", "u3"]


def test_missing_or_invalid_indices_fall_back_to_whole_batch():
    """Over-attributing provenance is recoverable; storing an event with none
    is not."""
    batch = [_row(1, "u1"), _row(2, "u2")]
    assert len(_rows_for_indices(batch, None)) == 2
    assert len(_rows_for_indices(batch, [])) == 2
    assert len(_rows_for_indices(batch, [99])) == 2
    assert len(_rows_for_indices(batch, ["x"])) == 2


# ---------------------------------------------------------------------------
# End-to-end batch behaviour
# ---------------------------------------------------------------------------

def test_mixed_batch_writes_one_event_per_type_with_own_sources():
    batch = [
        _row(1, "https://a.test/war", hours_old=1),
        _row(2, "https://b.test/sanctions", hours_old=30),
    ]
    scored = [
        _event("military_conflict", 0.8, indices=[1]),
        _event("sanctions", 0.6, indices=[2]),
    ]
    written: list[dict] = []

    with (
        patch.object(sentinel, "fetch_unprocessed_news", return_value=batch),
        patch.object(sentinel, "_select_balanced_batch", return_value=batch),
        patch.object(sentinel, "_call_gemini", return_value=scored),
        patch.object(sentinel, "upsert_risk_event", side_effect=written.append),
        patch.object(sentinel, "mark_news_processed", lambda ids: None),
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
    ):
        count = sentinel.process_unprocessed_batch()

    assert count == 2
    by_type = {e["disruption_type"]: e for e in written}
    assert set(by_type) == {"military_conflict", "sanctions"}

    # Each event carries only its own headline's URL...
    assert by_type["military_conflict"]["source_urls"] == ["https://a.test/war"]
    assert by_type["sanctions"]["source_urls"] == ["https://b.test/sanctions"]

    # ...and its own timestamp, so the newer story cannot reset the older
    # incident's decay clock.
    assert by_type["sanctions"]["source_fetched_at"] < by_type["military_conflict"]["source_fetched_at"]


def test_headline_indices_are_not_persisted():
    """It is prompt plumbing, not part of the stored event."""
    batch = [_row(1, "https://a.test/1")]
    written: list[dict] = []

    with (
        patch.object(sentinel, "fetch_unprocessed_news", return_value=batch),
        patch.object(sentinel, "_select_balanced_batch", return_value=batch),
        patch.object(sentinel, "_call_gemini", return_value=[_event("weather", indices=[1])]),
        patch.object(sentinel, "upsert_risk_event", side_effect=written.append),
        patch.object(sentinel, "mark_news_processed", lambda ids: None),
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
    ):
        sentinel.process_unprocessed_batch()

    assert "headline_indices" not in written[0]


def test_all_headlines_marked_processed_even_when_split():
    batch = [_row(1, "u1"), _row(2, "u2"), _row(3, "u3")]
    marked: list[list[int]] = []

    with (
        patch.object(sentinel, "fetch_unprocessed_news", return_value=batch),
        patch.object(sentinel, "_select_balanced_batch", return_value=batch),
        patch.object(sentinel, "_call_gemini", return_value=[_event("accident", indices=[2])]),
        patch.object(sentinel, "upsert_risk_event", lambda e: None),
        patch.object(sentinel, "mark_news_processed", side_effect=marked.append),
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
    ):
        sentinel.process_unprocessed_batch()

    # Otherwise unreferenced headlines would be re-scored forever.
    assert sorted(marked[0]) == [1, 2, 3]
