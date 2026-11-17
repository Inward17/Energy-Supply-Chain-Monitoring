"""Unknown chokepoints are rejected at the API edge, aliases are resolved, and
every registry chokepoint has an explicit SPR import-share assumption."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import api
from src.agents.spr_agent import _CHOKEPOINT_IMPORT_SHARE, calculate_spr_impact
from src.utils.constants import CHOKEPOINTS
from src.utils.schemas import RerouteRequest, SprRequest, WarRoomRequest


@pytest.mark.parametrize("model,extra", [
    (RerouteRequest, {}),
    (SprRequest, {"lead_time_days": 10}),
    (WarRoomRequest, {"scenario_name": "S", "disrupted_volume_mbpd": 1.0}),
])
def test_typo_is_rejected_on_every_request_type(model, extra):
    with pytest.raises(ValidationError):
        model(blocked_chokepoint="Strait of Hormuzs", **extra)


def test_alias_resolves_to_canonical_name():
    assert RerouteRequest(blocked_chokepoint=" Hormuz ").blocked_chokepoint == "Strait of Hormuz"


def test_every_registry_chokepoint_has_an_explicit_share():
    assert set(CHOKEPOINTS) <= set(_CHOKEPOINT_IMPORT_SHARE)


def test_spr_never_invents_a_share():
    with pytest.raises(ValueError):
        calculate_spr_impact(lead_time_days=10, blocked_chokepoint="Atlantis")


def test_api_returns_422_for_unknown_chokepoint():
    r = TestClient(api.app).post(
        "/api/orchestrator/spr", json={"blocked_chokepoint": "Strait of Hormuzs", "lead_time_days": 10}
    )
    assert r.status_code == 422
