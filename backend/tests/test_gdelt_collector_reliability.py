import pytest

from src.ingestion import gdelt_collector as collector


def test_queries_are_compact_stable_and_category_specific():
    maritime = collector._build_maritime_query()
    producer = collector._build_producer_query()

    assert maritime == collector.ENERGY_QUERY
    assert producer == collector.PRODUCER_QUERY
    assert len(maritime.encode("utf-8")) <= collector.GDELT_QUERY_MAX_BYTES
    assert len(producer.encode("utf-8")) <= collector.GDELT_QUERY_MAX_BYTES
    assert "Strait of Hormuz" in maritime
    assert "oil tanker" in maritime
    assert "refinery" in producer
    assert "attack" in producer
    assert ") AND (" in producer


def test_oversized_query_is_rejected_before_an_http_request(monkeypatch):
    def unexpected_client(*args, **kwargs):
        raise AssertionError("HTTP client must not be constructed")

    monkeypatch.setattr(collector.httpx, "Client", unexpected_client)

    with pytest.raises(ValueError, match="request query is"):
        collector._query_gdelt(
            {
                **collector.GDELT_PARAMS,
                "query": "x" * (collector.GDELT_QUERY_MAX_BYTES + 1),
            }
        )


def test_rate_limit_is_deferred_to_next_cycle_without_retry(monkeypatch):
    calls = []

    class Response:
        status_code = 429

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            calls.append((args, kwargs))
            return Response()

    monkeypatch.setattr(collector.httpx, "Client", Client)

    with pytest.raises(collector.RateLimitError):
        collector._query_gdelt(collector.GDELT_PARAMS)

    assert len(calls) == 1


def test_dual_query_keeps_two_request_cadence_and_chokepoint_priority(monkeypatch):
    calls = []
    sleeps = []

    def fake_query(params):
        calls.append(params["query"])
        if params["query"] == collector.ENERGY_QUERY:
            return [
                {
                    "url": "https://example.test/shared",
                    "title": "Strait of Hormuz tanker disruption",
                    "domain": "reuters.com",
                }
            ]
        assert params["query"] == collector.PRODUCER_QUERY
        return [
            {
                "url": "https://example.test/shared",
                "title": "Kuwait refinery shutdown",
                "domain": "reuters.com",
            },
            {
                "url": "https://example.test/producer",
                "title": "Kuwait refinery shutdown",
                "domain": "reuters.com",
            },
        ]

    monkeypatch.setattr(collector, "_query_gdelt", fake_query)
    monkeypatch.setattr(collector.time, "sleep", sleeps.append)

    articles = collector._fetch_dual_query("3d")
    by_url = {article["url"]: article for article in articles}

    assert calls == [collector.ENERGY_QUERY, collector.PRODUCER_QUERY]
    assert sleeps == [5.5]
    assert by_url["https://example.test/shared"]["_category"] == "chokepoint"
    assert by_url["https://example.test/producer"]["_category"] == "producer_nation"


def test_producer_query_results_require_a_producer_name_in_the_title(monkeypatch):
    monkeypatch.setattr(collector, "_get_producer_countries", lambda: ["Kuwait"])
    articles = [
        {
            "url": "https://example.test/maritime",
            "title": "Strait of Hormuz tanker disruption",
            "domain": "reuters.com",
            "_category": "chokepoint",
        },
        {
            "url": "https://example.test/kuwait",
            "title": "Kuwait refinery shutdown",
            "domain": "reuters.com",
            "_category": "producer_nation",
        },
        {
            "url": "https://example.test/no-country",
            "title": "European refinery shutdown",
            "domain": "reuters.com",
            "_category": "producer_nation",
        },
    ]

    filtered = collector._prefilter_articles(articles)

    assert {article["url"] for article in filtered} == {
        "https://example.test/maritime",
        "https://example.test/kuwait",
    }


def test_live_ingestion_runs_one_selected_query_per_cycle(monkeypatch):
    calls = []
    stored = []

    def fake_query(params):
        calls.append(params["query"])
        return [{
            "url": "https://example.test/kuwait-live",
            "title": "Kuwait oil refinery attack",
            "domain": "reuters.com",
        }]

    monkeypatch.setattr(collector, "_query_gdelt", fake_query)
    monkeypatch.setattr(
        collector,
        "_get_producer_countries",
        lambda: ["Kuwait"],
    )
    monkeypatch.setattr(
        collector,
        "upsert_news",
        lambda records: stored.extend(records) or len(records),
    )

    count = collector.fetch_and_store(category="producer_nation")

    assert calls == [collector.PRODUCER_QUERY]
    assert count == 1
    assert stored[0]["article_category"] == "producer_nation"
