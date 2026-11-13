"""AISStream HTTP 429 handling: retry with backoff instead of losing the window."""
import asyncio

import pytest
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from src.ingestion import ais_streamer as ais


@pytest.fixture
def no_db(monkeypatch):
    monkeypatch.setenv("AISSTREAM_API_KEY", "test-key")
    monkeypatch.setattr(ais, "fetch_vessel_types", lambda: {})
    monkeypatch.setattr(ais, "upsert_vessel_types", lambda rows: None)
    monkeypatch.setattr(ais, "upsert_vessel", lambda rows: len(rows))

    async def instant(_):
        return None

    monkeypatch.setattr(ais.asyncio, "sleep", instant)


def _fake_stream(throttles: int):
    calls = {"n": 0}

    async def fake(api_key, secs, buffer, *_):
        calls["n"] += 1
        if calls["n"] <= throttles:
            raise ais._Throttled
        buffer.append({"mmsi": 1})

    return fake, calls


def test_retries_after_429_then_stores(no_db, monkeypatch):
    fake, calls = _fake_stream(throttles=2)
    monkeypatch.setattr(ais, "_stream_snapshot", fake)
    assert ais.snapshot_vessels(1) == 1
    assert calls["n"] == 3


def test_gives_up_after_all_retries(no_db, monkeypatch):
    fake, calls = _fake_stream(throttles=99)
    monkeypatch.setattr(ais, "_stream_snapshot", fake)
    assert ais.snapshot_vessels(1) == 0
    assert calls["n"] == len(ais.THROTTLE_RETRY_DELAYS_SECONDS) + 1


def test_handshake_429_maps_to_throttled(monkeypatch):
    def reject(*_, **__):
        raise InvalidStatus(Response(429, "Too Many Requests", Headers()))

    monkeypatch.setattr(ais.websockets, "connect", reject)
    with pytest.raises(ais._Throttled):
        asyncio.run(ais._stream_snapshot("k", 1, [], {}, []))
