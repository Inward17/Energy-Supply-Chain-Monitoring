"""Graph migration scope, SPR arrival/refill, and sanctions labels."""
from unittest.mock import MagicMock, patch

from src.agents import fixer_agent as fixer
from src.agents.spr_agent import calculate_spr_impact
from src.database import neo4j_graph


# ── Neo4j migration ──────────────────────────────────────────────────────────

def test_old_schema_migration_only_deletes_app_labels():
    session = MagicMock()
    counts = iter([0, 7])  # ExportPort count, then total node count
    session.run.return_value.single.side_effect = lambda: {"n": next(counts)}
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session

    with patch.object(neo4j_graph, "get_driver", return_value=driver):
        try:
            neo4j_graph.seed_graph()
        except StopIteration:
            pass  # later seeding queries reuse the mock; only the delete matters

    deletes = [c for c in session.run.call_args_list if "DELETE" in c.args[0]]
    assert len(deletes) == 1
    query, kwargs = deletes[0].args[0], deletes[0].kwargs
    assert "MATCH (n) DETACH DELETE n" not in query
    assert set(kwargs["owned"]) == set(neo4j_graph.APP_LABELS)


# ── SPR arrival and refill ──────────────────────────────────────────────────

def _series(**kw):
    r = calculate_spr_impact(blocked_chokepoint="Strait of Hormuz", **kw)
    return r, r["burndown_df"]


def test_fractional_arrival_marker_matches_partial_day():
    _, df = _series(lead_time_days=2.5, run_rate_cut=0, industrial_cut=0, transport_cut=0)
    arrival = df.index[df["Ships Arrive"]].tolist()
    assert arrival == [2]
    levels = df["SPR Level (MB)"].tolist()
    drop_day1 = levels[0] - levels[1]
    drop_day2 = levels[1] - levels[2]
    # Day 2 is half depletion, half refill: smaller net drop than a full day.
    assert 0 < drop_day2 < drop_day1


def test_refill_share_is_configurable_and_disclosed():
    slow, df_slow = _series(lead_time_days=5, replenish_share=0.1)
    fast, df_fast = _series(lead_time_days=5, replenish_share=0.9)
    assert df_fast["SPR Level (MB)"].iloc[-1] > df_slow["SPR Level (MB)"].iloc[-1]
    assert any("refills at 90%" in a for a in fast["assumptions"])


# ── Sanctions labels ────────────────────────────────────────────────────────

def test_sanctioned_countries_are_labelled_including_blends():
    assert fixer._is_sanctioned("Russia")
    assert fixer._is_sanctioned("Nigeria + Iran")
    assert not fixer._is_sanctioned("Norway")


def test_reroute_rows_carry_sanctioned_flag():
    from tests.test_risk_aggregation import _make_port, _run_with_mocks

    rows = _run_with_mocks([_make_port("Primorsk", "Russia"), _make_port("Bonny", "Nigeria")], [])
    flags = {r["country"]: r["sanctioned"] for r in rows["procurement_matrix"]}
    assert flags == {"Russia": True, "Nigeria": False}
