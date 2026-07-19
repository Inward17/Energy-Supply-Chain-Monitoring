"""
tests/test_sentinel_canonicalization.py
───────────────────────────────────────
Verifies that Sentinel's parsing correctly canonicalizes chokepoint variants
and retains provenance logs, ensuring valid hits aren't silently dropped.
"""
from __future__ import annotations
import json
import logging
from src.agents.sentinel_agent import _parse_gemini_response

def test_chokepoint_canonicalization(caplog):
    """
    Test that aliases are correctly mapped to their canonical set equivalents
    and that a provenance log is emitted.
    """
    raw_response = json.dumps({
        "region": "Middle East",
        "disruption_type": "military_conflict",
        "severity": 0.8,
        "affected_chokepoints": ["Hormuz Strait", "Suez", "Strait of Malacca", "Unknown Strait"],
        "affected_producer_countries": [],
        "directly_affected_producer_countries": [],
        "confidence": 0.9,
        "severity_reasoning": "Test",
        "summary": "Test",
    })

    with caplog.at_level(logging.INFO):
        parsed = _parse_gemini_response(raw_response)
    
    cps = parsed.get("affected_chokepoints", [])
    assert "Strait of Hormuz" in cps
    assert "Suez Canal" in cps
    assert "Strait of Malacca" in cps
    assert "Unknown Strait" not in cps
    assert "Hormuz Strait" not in cps

    assert len(cps) == 3

    log_text = caplog.text
    assert "canonicalized chokepoint 'Hormuz Strait' -> 'Strait of Hormuz'" in log_text
    assert "canonicalized chokepoint 'Suez' -> 'Suez Canal'" in log_text
    assert "canonicalized chokepoint 'Strait of Malacca'" not in log_text
