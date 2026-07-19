import logging
import sys
from src.ingestion.gdelt_collector import fetch_and_store
from src.database.postgres_db import get_conn
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

print("Running fetch_and_store...")
fetch_and_store(timespan="15min")

with get_conn() as conn:
    print("\nRecent news_cache records:")
    rows = conn.execute(text("SELECT id, title, article_category, processed FROM news_cache ORDER BY fetched_at DESC LIMIT 10")).mappings().all()
    for r in rows:
        print(f"ID {r['id']} | Category: {r['article_category']} | Processed: {r['processed']} | Title: {r['title'][:60]}...")
