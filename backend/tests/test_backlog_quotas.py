"""
tests/test_backlog_quotas.py
────────────────────────────
Verifies that the `fetch_unprocessed_news` quota reservations hold
even under extreme skew (e.g., thousands of chokepoint articles, few general).
"""
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from src.database import postgres_db
from src.database.postgres_db import fetch_unprocessed_news

@pytest.fixture
def empty_news_cache():
    # Runs inside conftest's db_transaction rollback wrapper. get_conn must be
    # resolved through the module (not imported by name) so the monkeypatch
    # applies, and nothing here may commit: the DELETE stays visible to the
    # test via the shared patched connection and is rolled back afterwards,
    # leaving the live news_cache untouched.
    with postgres_db.get_conn() as conn:
        conn.execute(text("DELETE FROM news_cache"))
    yield

def test_fetch_unprocessed_news_quotas_under_extreme_skew(empty_news_cache):
    """
    If we have 900 chokepoint articles and 5 general articles, fetching with
    limit=50 should reserve space for the 5 general articles, preventing starvation.
    """
    now = datetime.now(timezone.utc)
    
    # Insert 900 chokepoint articles
    cp_rows = []
    for i in range(900):
        ts = now - timedelta(hours=10) # 10 hours old
        cp_rows.append({
            "url": f"http://test.com/cp/{i}",
            "title": f"Chokepoint News {i}",
            "source": "GDELT",
            "fetched_at": ts,
            "processed": False,
            "article_category": "chokepoint"
        })
        
    # Insert 5 general articles
    gen_rows = []
    for i in range(5):
        ts = now - timedelta(hours=20) # 20 hours old (older)
        gen_rows.append({
            "url": f"http://test.com/gen/{i}",
            "title": f"General News {i}",
            "source": "GDELT",
            "fetched_at": ts,
            "processed": False,
            "article_category": "general"
        })
        
    with postgres_db.get_conn() as conn:
        for chunk in [cp_rows[i:i + 100] for i in range(0, len(cp_rows), 100)]:
            conn.execute(text(
                "INSERT INTO news_cache (url, title, source, fetched_at, processed, article_category) "
                "VALUES (:url, :title, :source, :fetched_at, :processed, :article_category)"
            ), chunk)
        conn.execute(text(
            "INSERT INTO news_cache (url, title, source, fetched_at, processed, article_category) "
            "VALUES (:url, :title, :source, :fetched_at, :processed, :article_category)"
        ), gen_rows)

    # Fetch with limit=50 (candidate pool size for batch_size=10)
    # Quotas: CP=20, Prod=15, Gen=15
    rows = fetch_unprocessed_news(limit=50)
    
    # Assert we got some rows
    assert len(rows) > 0
    
    categories = [r["article_category"] for r in rows]
    cp_count = categories.count("chokepoint")
    gen_count = categories.count("general")
    
    assert cp_count == 20, f"Expected 20 chokepoint articles (40% quota), got {cp_count}"
    assert gen_count == 5, f"Expected all 5 general articles to survive starvation, got {gen_count}"

