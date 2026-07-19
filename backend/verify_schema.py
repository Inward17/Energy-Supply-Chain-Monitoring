import logging
import sys

from src.database.postgres_db import init_schema, get_conn
from sqlalchemy import text
from src.ingestion.gdelt_collector import _build_producer_query

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

print("1. Initialising Schema...")
init_schema()

print("2. Checking 'article_category' column in news_cache...")
with get_conn() as conn:
    res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='news_cache' AND column_name='article_category'")).first()
    if res:
        print("-> Column article_category exists in news_cache!")
    else:
        print("-> ERROR: Column article_category missing in news_cache!")

    res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='risk_events' AND column_name='article_category'")).first()
    if res:
        print("-> Column article_category exists in risk_events!")
    else:
        print("-> ERROR: Column article_category missing in risk_events!")

print("3. Query B output:")
query_b = _build_producer_query()
print("->", query_b)

print("Check successful!")
