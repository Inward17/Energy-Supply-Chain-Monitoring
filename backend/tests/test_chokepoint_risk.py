"""
tests/test_chokepoint_risk.py
─────────────────────────────
Verifies that chokepoint risk aggregation correctly distinguishes between
directly affected (full risk) and indirectly affected (discounted risk)
chokepoints, and applies max() aggregation.
"""
from datetime import datetime, timezone
from src.agents.modeler_agent import _active_chokepoint_risks
from src.utils.constants import CHOKEPOINT_INDIRECT_MENTION_DISCOUNT, MODELER_BASELINE_RISK

def test_chokepoint_direct_vs_indirect_risk():
    now = datetime.now(timezone.utc)
    # severity=0.8, no decay needed for exactly now
    events = [{
        "severity": 0.8,
        "disruption_type": "military_conflict",
        "created_at": now,
        "affected_chokepoints": ["Strait of Hormuz", "Bab-el-Mandeb"],
        "directly_affected_chokepoints": ["Strait of Hormuz"]
    }]
    
    risk, prov = _active_chokepoint_risks(events, now)
    
    # Strait of Hormuz is direct, gets full risk (0.8)
    assert abs(risk.get("Strait of Hormuz", 0) - 0.8) < 0.001
    
    # Bab-el-Mandeb is indirect (affected - direct), gets discounted risk
    expected_indirect = 0.8 * CHOKEPOINT_INDIRECT_MENTION_DISCOUNT
    assert abs(risk.get("Bab-el-Mandeb", 0) - expected_indirect) < 0.001


def test_chokepoint_legacy_null_direct_field_gets_full_risk():
    """Rows written before the direct/indirect split have NULL (None) in
    directly_affected_chokepoints. They were scored at full severity and must
    not be retroactively discounted as 'indirect mentions'."""
    now = datetime.now(timezone.utc)
    events = [{
        "severity": 0.8,
        "disruption_type": "military_conflict",
        "created_at": now,
        "affected_chokepoints": ["Strait of Hormuz"],
        "directly_affected_chokepoints": None,  # legacy SQL NULL
    }]

    risk, _ = _active_chokepoint_risks(events, now)

    assert abs(risk.get("Strait of Hormuz", 0) - 0.8) < 0.001


def test_chokepoint_explicit_empty_direct_field_stays_discounted():
    """An explicit empty list is a scorer judgement (nothing directly hit),
    unlike NULL, so the indirect discount still applies."""
    now = datetime.now(timezone.utc)
    events = [{
        "severity": 0.8,
        "disruption_type": "military_conflict",
        "created_at": now,
        "affected_chokepoints": ["Strait of Hormuz"],
        "directly_affected_chokepoints": [],
    }]

    risk, _ = _active_chokepoint_risks(events, now)

    expected = 0.8 * CHOKEPOINT_INDIRECT_MENTION_DISCOUNT
    assert abs(risk.get("Strait of Hormuz", 0) - expected) < 0.001


def test_chokepoint_max_aggregation():
    now = datetime.now(timezone.utc)
    # Event 1: Bab-el-Mandeb indirect, severity 0.6 -> discounted 0.3
    # Event 2: Bab-el-Mandeb indirect, severity 0.8 -> discounted 0.4
    events = [
        {
            "severity": 0.6,
            "disruption_type": "military_conflict",
            "created_at": now,
            "affected_chokepoints": ["Bab-el-Mandeb"],
            "directly_affected_chokepoints": []
        },
        {
            "severity": 0.8,
            "disruption_type": "military_conflict",
            "created_at": now,
            "affected_chokepoints": ["Bab-el-Mandeb"],
            "directly_affected_chokepoints": []
        }
    ]
    
    risk, prov = _active_chokepoint_risks(events, now)
    
    expected = 0.8 * CHOKEPOINT_INDIRECT_MENTION_DISCOUNT
    assert abs(risk.get("Bab-el-Mandeb", 0) - expected) < 0.001

def test_chokepoint_direct_overrides_indirect():
    now = datetime.now(timezone.utc)
    # Event 1: Bab-el-Mandeb indirect, severity 0.8 -> discounted 0.4
    # Event 2: Bab-el-Mandeb direct, severity 0.6 -> full 0.6
    # Max should be 0.6
    events = [
        {
            "severity": 0.8,
            "disruption_type": "military_conflict",
            "created_at": now,
            "affected_chokepoints": ["Bab-el-Mandeb"],
            "directly_affected_chokepoints": []
        },
        {
            "severity": 0.6,
            "disruption_type": "military_conflict",
            "created_at": now,
            "affected_chokepoints": ["Bab-el-Mandeb"],
            "directly_affected_chokepoints": ["Bab-el-Mandeb"]
        }
    ]
    
    risk, prov = _active_chokepoint_risks(events, now)
    
    assert abs(risk.get("Bab-el-Mandeb", 0) - 0.6) < 0.001
