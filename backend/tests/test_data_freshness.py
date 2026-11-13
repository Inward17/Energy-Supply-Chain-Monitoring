"""Fixes for stale production data: Gemini 503 fallback, empty-batch marking,
and the --with jobs used by the scheduled GitHub Actions run."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import cron_worker
from src.agents import sentinel_agent as sentinel


class _FakeModels:
    def __init__(self, fail_with: dict[str, Exception]):
        self.fail_with = fail_with
        self.calls: list[str] = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        if model in self.fail_with:
            raise self.fail_with[model]
        return SimpleNamespace(text=f"from {model}")


def _client(fail_with):
    return SimpleNamespace(models=_FakeModels(fail_with))


def test_overloaded_primary_falls_back_to_lighter_model():
    client = _client({sentinel.SENTINEL_GEMINI_MODEL: RuntimeError("503 UNAVAILABLE")})
    response = sentinel.generate_with_fallback(client, "p", temperature=0.1)
    assert response.text == f"from {sentinel.GEMINI_FALLBACK_MODEL}"
    assert client.models.calls == [sentinel.SENTINEL_GEMINI_MODEL, sentinel.GEMINI_FALLBACK_MODEL]


def test_other_errors_do_not_switch_model():
    client = _client({sentinel.SENTINEL_GEMINI_MODEL: RuntimeError("429 RESOURCE_EXHAUSTED")})
    with pytest.raises(RuntimeError, match="429"):
        sentinel.generate_with_fallback(client, "p", temperature=0.1)
    assert client.models.calls == [sentinel.SENTINEL_GEMINI_MODEL]


def _run_batch(scored):
    batch = [{"id": 7, "title": "Tanker seized near Hormuz", "url": "https://a.test/1",
              "fetched_at": datetime.now(timezone.utc), "article_category": "chokepoint"}]
    marked: list[list[int]] = []
    with (
        patch.object(sentinel, "fetch_unprocessed_news", return_value=batch),
        patch.object(sentinel, "_select_balanced_batch", return_value=batch),
        patch.object(sentinel, "_call_gemini", return_value=scored),
        patch.object(sentinel, "mark_news_processed", side_effect=marked.append),
        patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
    ):
        assert sentinel.process_unprocessed_batch() == 0
    return marked


def test_empty_answer_marks_batch_processed():
    assert _run_batch([]) == [[7]]


def test_failed_call_leaves_batch_for_next_cycle():
    assert _run_batch(None) == []


def test_parse_extra_jobs():
    assert cron_worker._parse_extra_jobs(" ais, retention ") == ["ais", "retention"]
    assert cron_worker._parse_extra_jobs("") == []
    with pytest.raises(SystemExit):
        cron_worker._parse_extra_jobs("ais,nope")
